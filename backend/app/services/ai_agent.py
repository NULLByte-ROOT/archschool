import asyncio
import json
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
import httpx
from sqlalchemy import select, or_
from sqlalchemy.orm import Session

from .. import models
from ..analytics import build_leaderboard
from . import school_knowledge

logger = logging.getLogger("archschool.ai_agent")

_shared_client: Optional[httpx.AsyncClient] = None
_warp_client: Optional[httpx.AsyncClient] = None


def get_shared_client() -> httpx.AsyncClient:
    """Persistent connection pool to prevent per-request TLS handshake and TCP latency."""
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.AsyncClient(
            timeout=30.0,
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=50, keepalive_expiry=60.0),
        )
    return _shared_client


def get_warp_proxy_url() -> Optional[str]:
    """Retrieve Cloudflare WARP SOCKS5 IPv6 proxy URL (e.g. socks5://host.docker.internal:40000)."""
    import os
    val = os.getenv("WARP_PROXY", "socks5://host.docker.internal:40000").strip()
    return val if val and val.lower() not in ("none", "false", "0", "") else None


def get_warp_client() -> httpx.AsyncClient:
    """Persistent connection pool routed through Cloudflare WARP SOCKS5 IPv6 proxy for Google Gemini."""
    global _warp_client
    proxy_url = get_warp_proxy_url()
    if _warp_client is None or _warp_client.is_closed:
        _warp_client = httpx.AsyncClient(
            timeout=30.0,
            proxy=proxy_url,
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=50, keepalive_expiry=60.0),
        )
    return _warp_client

_prompt_cache: Optional[Dict[str, Any]] = None
def invalidate_prompt_cache() -> None:
    """Compatibility no-op since prompts are now read in real-time without caching."""
    pass


def get_ai_prompts_and_config(db: Session) -> Dict[str, Any]:
    """Retrieve system instruction, anchors, temperature, and max_tokens directly from DB with zero cache delay."""
    from ..prompts import default_prompts

    try:
        settings_rows = db.query(models.BotSetting).all()
        data = {s.key: s.value for s in settings_rows}
    except Exception as exc:
        logger.warning("Could not read BotSetting from DB, falling back to defaults: %s", exc)
        data = {}

    system_prompt = data.get("ai_system_prompt") if data.get("ai_system_prompt") is not None else default_prompts.DEFAULT_SYSTEM_PROMPT
    persona_anchor = data.get("ai_persona_anchor") if data.get("ai_persona_anchor") is not None else default_prompts.DEFAULT_PERSONA_ANCHOR
    followup_anchor = data.get("ai_followup_anchor") if data.get("ai_followup_anchor") is not None else default_prompts.DEFAULT_FOLLOWUP_ANCHOR

    try:
        temp = float(data.get("ai_temperature", default_prompts.DEFAULT_TEMPERATURE))
    except (ValueError, TypeError):
        temp = default_prompts.DEFAULT_TEMPERATURE

    try:
        max_tokens = int(data.get("ai_max_tokens", default_prompts.DEFAULT_MAX_TOKENS))
    except (ValueError, TypeError):
        max_tokens = default_prompts.DEFAULT_MAX_TOKENS

    return {
        "system_prompt": system_prompt,
        "persona_anchor": persona_anchor,
        "followup_anchor": followup_anchor,
        "temperature": temp,
        "max_tokens": max_tokens,
    }

OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_my_status",
            "description": "دریافت آمار شخصی کاربر، استریک، رتبه در لیدربورد و لیست تکالیف فعال و باقی‌مانده‌ای که هنوز انجام نداده است",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_class_assignments",
            "description": "دریافت لیست تکالیف فعال و جاری کلاس (فقط تکالیفی که مهلت تحویل آن‌ها معتبر است و منقضی نشده‌اند)",
            "parameters": {
                "type": "object",
                "properties": {
                    "subject": {
                        "type": "string",
                        "description": "نام یا شناسه درس برای فیلتر اختصاصی (مثلاً ریاضی، شیمی، طراحی وب، فارسی)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "تعداد تکالیف برای نمایش (پیش‌فرض ۵)",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_leaderboard",
            "description": "مشاهده جدول رتبه‌بندی برتر کلاس (لیدربورد)، درصد موفقیت و استریک‌های برتر",
            "parameters": {
                "type": "object",
                "properties": {
                    "top_n": {
                        "type": "integer",
                        "description": "تعداد نفرات برتر برای نمایش (پیش‌فرض ۵)",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_school_schedule",
            "description": "دریافت برنامه زمانی کلاس‌ها، دروس، نام دبیران و زنگ‌های مدرسه برای یک روز خاص یا کل هفته",
            "parameters": {
                "type": "object",
                "properties": {
                    "day": {
                        "type": "string",
                        "description": "روز مورد نظر برای دریافت برنامه (مثلاً: امروز، فردا، شنبه، یکشنبه، دوشنبه، سه‌شنبه، چهارشنبه، یا کل هفته)",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "toggle_assignment_completion",
            "description": "علامت‌زدن یا برداشتن علامت انجام تکالیف (تیک زدن انجام دادم یا برگرداندن تیک) برای کاربر فعلی",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["complete", "uncomplete"],
                        "description": "عملیات مورد نظر: complete (تیک زدن به عنوان انجام‌شده) یا uncomplete (برداشتن تیک)",
                    },
                    "scope": {
                        "type": "string",
                        "enum": ["single", "day", "all"],
                        "description": "دامنه تیک زدن: single (یک تکلیف خاص با نام/شناسه)، day (تمام تکالیف یک روز خاص مثل شنبه)، all (تمام تکالیف باقیمانده)",
                    },
                    "assignment_query": {
                        "type": "string",
                        "description": "نام یا شناسه تکلیف برای حالت single (مثلاً ریاضی، تمرین صفحه ۲۰، طراحی وب)",
                    },
                    "target_day": {
                        "type": "string",
                        "description": "نام روز برای حالت scope='day' (مثلاً: شنبه، یکشنبه، دوشنبه، سه‌شنبه، چهارشنبه، امروز، فردا)",
                    },
                },
                "required": ["scope"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_assignment_completions",
            "description": "استعلام و بررسی دقیق این‌که چه کسانی یک تکلیف یا درس خاص را انجام داده و تیک زده‌اند و چه کسانی هنوز انجام نداده‌اند. هر زمان هر کاربری پرسید «کیا فلان تکلیف رو انجام دادن»، «کی‌ها تیک زدن»، «کیا فرستادن/کامل کردن»، یا آمار انجام و تحویل یک تکلیف را خواست، حتماً این ابزار را فراخوانی کن.",
            "parameters": {
                "type": "object",
                "properties": {
                    "assignment_query": {
                        "type": "string",
                        "description": "نام یا کلمات کلیدی تکلیف یا درس (مثلاً: ریاضی، شیمی، تمرین صفحه ۲۰، طراحی وب)",
                    },
                },
                "required": ["assignment_query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_add_homework_wizard",
            "description": "باز کردن و ارسال منوی تعاملی و دکمه‌ای هوشمند برای افزودن یا ثبت تکلیف، مشق، امتحان، پروژه یا یادآوری جدید در مدرسه. هر زمان کاربر تمایل به ایجاد، ثبت، تعریف، یا افزودن تکلیف یا یادآوری جدید داشت، این ابزار را فراخوانی کن.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "render_visual_card",
            "description": "رندر و تولید اسکرین‌شات گرافیکی بسیار زیبا و تمیز از کارت‌ها و نمودارهای اپلیکیشن (شامل: کارنامه و نمودار پیشرفت تحصیلی دانش‌آموز، چارت جدول لیدربورد و سکوی قهرمانی، چارت برنامه هفتگی و زنگ‌ها، یا کارت تکالیف فعال). هر زمان کاربر گفت 'نمودار درست کن'، 'نمودار'، 'چارت'، 'کارنامه' یا خواستار دیدن نمودار یا تصویر وضعیت شد، باید بلافاصله این ابزار را فراخوانی کنی.",
            "parameters": {
                "type": "object",
                "properties": {
                    "card_type": {
                        "type": "string",
                        "enum": ["progress", "leaderboard", "schedule", "assignments"],
                        "description": "نوع کارت تصویری: 'progress' (کارنامه و نمودار پیشرفت تحصیلی)، 'leaderboard' (سکوی قهرمانی و رتبه‌بندی)، 'schedule' (برنامه هفتگی و زنگ‌ها)، 'assignments' (تکالیف فعال و جاری)",
                    },
                    "target_day": {
                        "type": "string",
                        "description": "روز مشخص برای رندر کارت تکالیف یا برنامه (مثلاً: 'امروز'، 'فردا'، 'پس‌فردا'، 'شنبه'، 'یکشنبه'، 'دوشنبه'، 'سه‌شنبه'، 'چهارشنبه'). اگر کاربر تکالیف یا برنامه روز خاصی مثل فردا را خواست، این پارامتر را پر کن.",
                    },
                    "subject": {
                        "type": "string",
                        "description": "نام یا شناسه درس در صورت نیاز به فیلتر برنامه",
                    },
                },
                "required": ["card_type"],
            },
        },
    },
]


def execute_check_assignment_completions(db: Session, query_str: str) -> Dict[str, Any]:
    """Check who has completed (ticked) a specific assignment and who has not."""
    clean_q = (query_str or "").strip()
    # Normalize common Persian prefixes/fillers
    fillers = (
        "کیا", "کی‌ها", "کی ها", "چه کسانی", "کدوم بچه‌ها", "کدام بچه‌ها", "رو", "را",
        "تکلیف", "مشق", "درس", "انجام دادن", "انجام داده", "انجام دادند", "تیک زدن",
        "تیک زده", "تیک زدند", "تیک زدنش", "حل کردن", "حل کرده", "نوشتن", "نوشته",
        "کامل کردن", "کامل کرده", "فرستادن", "فرستاده", "کامل شد", "وضعیت", "چک کن", "ببین"
    )
    for w in fillers:
        clean_q = re.sub(rf'\b{re.escape(w)}\b', ' ', clean_q)
        clean_q = clean_q.replace(w, ' ')
    clean_q = re.sub(r'[\?\!؟،,]+', ' ', clean_q)
    clean_q = re.sub(r'\s+', ' ', clean_q).strip()

    base_q = db.query(models.Assignment).filter(models.Assignment.deleted_at.is_(None))
    candidates: List[models.Assignment] = []

    if clean_q:
        candidates = base_q.filter(
            or_(
                models.Assignment.title.ilike(f"%{clean_q}%"),
                models.Assignment.course.ilike(f"%{clean_q}%"),
                models.Assignment.subject_id.ilike(f"%{clean_q}%"),
                models.Assignment.description.ilike(f"%{clean_q}%"),
            )
        ).all()

        if not candidates and " " in clean_q:
            for word in clean_q.split():
                if len(word) >= 2:
                    sub_c = base_q.filter(
                        or_(
                            models.Assignment.title.ilike(f"%{word}%"),
                            models.Assignment.course.ilike(f"%{word}%"),
                            models.Assignment.subject_id.ilike(f"%{word}%"),
                        )
                    ).all()
                    if sub_c:
                        candidates.extend(sub_c)
            seen = set()
            dedup = []
            for c in candidates:
                if c.id not in seen:
                    seen.add(c.id)
                    dedup.append(c)
            candidates = dedup

    if not candidates and not clean_q:
        candidates = base_q.order_by(models.Assignment.due_date.asc().nulls_last()).all()

    if not candidates:
        return {
            "success": False,
            "message": f"تکلیفی متناسب با «{query_str}» در سیستم پیدا نشد. لطفاً نام درس یا عنوان تکلیف را مشخص‌تر بفرمایید.",
        }

    # Sort candidates: active (non-overdue) first, then nearest due date or newest created
    candidates.sort(
        key=lambda a: (
            1 if school_knowledge.is_assignment_overdue(a.due_date, a.subject_id) else 0,
            a.due_date or datetime.max,
        )
    )
    target = candidates[0]

    completions = (
        db.query(models.AssignmentCompletion)
        .filter(models.AssignmentCompletion.assignment_id == target.id)
        .all()
    )
    completed_user_ids = {c.user_id for c in completions}

    all_users = (
        db.query(models.User)
        .filter(models.User.is_active.is_(True))
        .order_by(models.User.username.asc())
        .all()
    )

    def format_name(u: models.User) -> str:
        fn = getattr(u, "full_name", None)
        return f"{fn} ({u.username})" if fn and fn.strip() else u.username

    completed_list = [format_name(u) for u in all_users if u.id in completed_user_ids]
    pending_list = [format_name(u) for u in all_users if u.id not in completed_user_ids]

    total_count = len(all_users)
    done_count = len(completed_list)
    pending_count = len(pending_list)
    pct = round((done_count / total_count * 100), 1) if total_count > 0 else 0.0
    rel_due = school_knowledge.format_due_date_relative(target.due_date) if target.due_date else "بدون مهلت خاص"

    return {
        "success": True,
        "assignment_id": target.id,
        "title": target.title,
        "course": target.course or "عمومی",
        "due_date_relative": rel_due,
        "is_overdue": school_knowledge.is_assignment_overdue(target.due_date, target.subject_id),
        "total_students": total_count,
        "completed_count": done_count,
        "pending_count": pending_count,
        "completion_percentage": pct,
        "completed_students": completed_list,
        "pending_students": pending_list,
        "summary": f"{done_count} نفر از {total_count} نفر ({pct}٪) تکلیف «{target.title}» را انجام داده و تیک زده‌اند.",
    }


def format_assignment_completions_html(data: Dict[str, Any]) -> str:
    """Format check_assignment_completions output for Telegram HTML."""
    if not data.get("success"):
        return f"⚠️ {data.get('message', 'تکلیف مورد نظر پیدا نشد.')}"

    title = data["title"]
    course = data.get("course") or "عمومی"
    rel_due = data.get("due_date_relative", "")
    comp_list = data.get("completed_students", [])
    pend_list = data.get("pending_students", [])
    done_cnt = data.get("completed_count", 0)
    pend_cnt = data.get("pending_count", 0)
    total_cnt = data.get("total_students", 0)
    pct = data.get("completion_percentage", 0.0)

    if comp_list:
        comp_str = "\n".join([f"🔹 {name}" for name in comp_list])
    else:
        comp_str = "<i>هنوز هیچ‌یک از دانش‌آموزان این تکلیف را تیک نزده‌اند.</i>"

    if pend_list:
        pend_str = "\n".join([f"▫️ {name}" for name in pend_list])
    else:
        pend_str = "<i>آفرین به همه! تمام دانش‌آموزان این تکلیف را کامل کرده‌اند! 👏🔥</i>"

    return (
        f"📋 <b>گزارش وضعیت انجام تکلیف کلاسی</b>\n\n"
        f"📌 <b>تکلیف:</b> <b>{title}</b> ({course})\n"
        f"📅 <b>مهلت تحویل:</b> {rel_due}\n"
        f"────────────────────\n"
        f"✅ <b>تیک زده و انجام داده‌اند ({done_cnt} نفر):</b>\n"
        f"{comp_str}\n\n"
        f"⏳ <b>هنوز انجام نداده‌اند ({pend_cnt} نفر):</b>\n"
        f"{pend_str}\n"
        f"────────────────────\n"
        f"📊 <b>پیشرفت کلاس:</b> <b>{pct}٪</b> ({done_cnt} از {total_cnt} نفر)"
    )


def execute_tool(
    name: str, args: Dict[str, Any], db: Session, current_user: Optional[models.User]
) -> Dict[str, Any]:
    """Execute python functions corresponding to function calls."""
    try:
        if name == "check_assignment_completions":
            q_text = (args.get("assignment_query") or "").strip()
            return execute_check_assignment_completions(db, q_text)

        elif name == "get_my_status":
            if not current_user:
                return {
                    "success": False,
                    "message": "اکانت تلگرام شما هنوز به حساب کاربری ArchSchool لینک نشده است. لطفاً کد اتصال اختصاصی خود را از تب پروفایل اپلیکیشن کپی کرده و در پیوی ربات بفرستید تا حساب شما متصل شود.",
                }

            entries, _ = build_leaderboard(db)
            user_entry = next((e for e in entries if e["user"].id == current_user.id), None)
            now = datetime.utcnow()

            # Find uncompleted assignments that are currently ACTIVE (deadline strictly not expired)
            completed_ids = (
                select(models.AssignmentCompletion.assignment_id)
                .filter(models.AssignmentCompletion.user_id == current_user.id)
            )
            raw_pending = (
                db.query(models.Assignment)
                .filter(
                    models.Assignment.deleted_at.is_(None),
                    ~models.Assignment.id.in_(completed_ids),
                )
                .order_by(
                    models.Assignment.due_date.asc().nulls_last(),
                    models.Assignment.created_at.desc(),
                )
                .all()
            )
            pending = [
                a for a in raw_pending
                if not school_knowledge.is_assignment_overdue(a.due_date, a.subject_id)
            ][:5]

            pending_list = []
            for a in pending:
                subj_info = school_knowledge.resolve_subject(a.subject_id or a.category or a.course or "")
                subj_name = subj_info["name"] if subj_info else (a.subject_id or a.category or a.course or "عمومی")
                teacher_name = subj_info["teacher"] if subj_info else "دبیر مربوطه"
                rel_due = school_knowledge.format_due_date_relative(a.due_date)
                pending_list.append({
                    "id": a.id,
                    "title": a.title,
                    "subject": subj_name,
                    "teacher": teacher_name,
                    "due_date_relative": rel_due,
                    "due_date": a.due_date.strftime("%Y-%m-%d %H:%M") if a.due_date else "بدون مهلت خاص",
                    "is_active": True,
                })

            return {
                "success": True,
                "username": current_user.username,
                "role": current_user.role,
                "rank": user_entry.get("rank") if user_entry else "نامشخص",
                "current_streak": user_entry.get("current_streak", 0) if user_entry else 0,
                "best_streak": user_entry.get("best_streak", 0) if user_entry else 0,
                "completion_percentage": round(user_entry.get("completion_percentage", 0), 1) if user_entry else 0,
                "pending_assignments": pending_list,
                "pending_count": len(pending_list),
                "has_pending": len(pending_list) > 0,
            }

        elif name == "get_class_assignments":
            limit = args.get("limit", 5)
            subject_filter = args.get("subject", "").strip()
            now = datetime.utcnow()

            query = db.query(models.Assignment).filter(
                models.Assignment.deleted_at.is_(None),
            )

            # Apply subject filter if specified
            if subject_filter:
                resolved = school_knowledge.resolve_subject(subject_filter)
                s_id = resolved["id"] if resolved else subject_filter
                s_name = resolved["name"] if resolved else subject_filter
                query = query.filter(
                    or_(
                        models.Assignment.subject_id.ilike(f"%{s_id}%"),
                        models.Assignment.subject_id.ilike(f"%{s_name}%"),
                        models.Assignment.category.ilike(f"%{s_name}%"),
                        models.Assignment.course.ilike(f"%{s_name}%"),
                        models.Assignment.title.ilike(f"%{s_name}%"),
                    )
                )

            query = query.order_by(
                models.Assignment.due_date.asc().nulls_last(),
                models.Assignment.created_at.desc(),
            )

            assignments_raw = query.all()
            # Strictly filter out any overdue assignments
            assignments = [
                a for a in assignments_raw
                if not school_knowledge.is_assignment_overdue(a.due_date, a.subject_id)
            ][:limit]

            if not assignments:
                msg = f"در حال حاضر هیچ تکلیف فعالی برای درس '{subject_filter}' وجود ندارد." if subject_filter else "در حال حاضر هیچ تکلیف فعالی با مهلت تحویل باز در اپلیکیشن وجود ندارد."
                return {
                    "success": True,
                    "assignments": [],
                    "total_count": 0,
                    "message": msg,
                }

            out_list = []
            for a in assignments:
                subj_info = school_knowledge.resolve_subject(a.subject_id or a.category or a.course or "")
                subj_name = subj_info["name"] if subj_info else (a.subject_id or a.category or a.course or "عمومی")
                teacher_name = subj_info["teacher"] if subj_info else "دبیر مربوطه"
                rel_due = school_knowledge.format_due_date_relative(a.due_date)
                out_list.append({
                    "id": a.id,
                    "title": a.title,
                    "description": a.description,
                    "subject": subj_name,
                    "teacher": teacher_name,
                    "due_date_relative": rel_due,
                    "due_date": a.due_date.strftime("%Y-%m-%d %H:%M") if a.due_date else "بدون مهلت خاص",
                    "is_expired": False,
                })

            return {
                "success": True,
                "total_count": len(out_list),
                "assignments": out_list,
            }

        elif name == "get_leaderboard":
            top_n = args.get("top_n", 5)
            entries, _ = build_leaderboard(db)
            top_list = []
            for e in entries[:top_n]:
                u = e["user"]
                top_list.append({
                    "rank": e.get("rank"),
                    "username": u.username,
                    "percentage": round(e.get("completion_percentage", 0), 1),
                    "streak": e.get("current_streak", 0),
                    "completed_count": e.get("completed_count", 0),
                })
            return {"success": True, "top_students": top_list}

        elif name == "get_school_schedule":
            day_query = args.get("day", "").strip().lower()
            current_status = school_knowledge.get_current_school_status()

            target_day_key = None
            if day_query:
                if any(x in day_query for x in ["امروز", "today"]):
                    target_day_key = current_status["day_key"]
                elif any(x in day_query for x in ["فردا", "tomorrow"]):
                    now_iran = school_knowledge.get_iran_now()
                    tomorrow = now_iran + timedelta(days=1)
                    target_day_key = school_knowledge.WEEKDAYS_MAP.get(tomorrow.weekday(), ("sat", "شنبه"))[0]
                elif any(x in day_query for x in ["بعدی", "روز مدرسه"]):
                    target_day_key = current_status.get("next_school_key", "sat")
                else:
                    target_day_key = school_knowledge.DAY_LOOKUP.get(day_query)

            if target_day_key and target_day_key in school_knowledge.WEEKLY_SCHEDULE:
                day_info = school_knowledge.WEEKLY_SCHEDULE[target_day_key]
                return {
                    "success": True,
                    "day": day_info["day_fa"],
                    "is_school_day": day_info["is_school_day"],
                    "periods": day_info["periods"],
                    "note": day_info.get("note", ""),
                    "current_bell_status": current_status["bell_status"],
                }

            # Return full weekly schedule if no specific day requested
            return {
                "success": True,
                "current_status": current_status,
                "weekly_schedule": school_knowledge.WEEKLY_SCHEDULE,
                "bell_times": [
                    {"period": 1, "time": "08:00 تا 09:30"},
                    {"period": 2, "time": "09:30 تا 11:00"},
                    {"period": 3, "time": "11:00 تا 12:30"},
                    {"period": 4, "time": "12:30 تا 14:00"},
                ],
            }

        elif name == "add_assignment":
            if not current_user or not (current_user.is_admin or current_user.role in ("admin", "owner")):
                return {
                    "success": False,
                    "error": "عدم دسترسی! در اپلیکیشن ArchSchool فقط ادمین یا مالک مدرسه مجاز به ثبت تکلیف جدید هستند.",
                }

            title = args.get("title", "").strip()
            description = args.get("description", "").strip()
            due_str = args.get("due_date", "").strip()
            subject = args.get("subject", "").strip()

            if not title:
                return {"success": False, "error": "عنوان تکلیف الزامی است."}

            due_dt = None
            if due_str:
                try:
                    due_dt = datetime.fromisoformat(due_str.replace("Z", "+00:00"))
                except Exception:
                    due_dt = datetime.now(timezone.utc)

            subj_info = school_knowledge.resolve_subject(subject)
            s_id = subj_info["id"] if subj_info else subject
            s_name = subj_info["name"] if subj_info else subject
            is_reminder = bool(args.get("is_reminder_only", False))

            new_assignment = models.Assignment(
                title=title,
                description=description,
                due_date=due_dt,
                subject_id=s_id,
                category=s_name,
                course=s_name,
                is_reminder_only=is_reminder,
                owner_id=current_user.id,
                creator_id=current_user.id,
            )
            db.add(new_assignment)
            # Creator reward: adding an assignment counts towards daily activity
            from ..routers.assignments import _record_daily_activity
            _record_daily_activity(db, current_user.id, datetime.utcnow(), +1)
            db.commit()
            db.refresh(new_assignment)

            from .. import notifications
            notifications.notify_new_assignment(db, new_assignment)

            return {
                "success": True,
                "message": f"تکلیف '{title}' با موفقیت توسط {current_user.username} در اپلیکیشن ثبت شد و امتیاز فعالیت به شما تعلق گرفت!",
                "assignment_id": new_assignment.id,
            }

        elif name == "toggle_assignment_completion":
            if not current_user:
                return {
                    "success": False,
                    "message": "برای تیک زدن تکالیف، ابتدا باید اکانت تلگرام خود را به حساب ArchSchool متصل کنید. کد اتصال اختصاصی خود را از اپلیکیشن بگیرید و بفرستید.",
                }

            action = args.get("action", "complete")
            scope = args.get("scope", "single")
            assignment_query = args.get("assignment_query", "").strip()
            target_day = args.get("target_day", "").strip()
            now = datetime.utcnow()

            target_assignments = []
            if scope == "single":
                q = db.query(models.Assignment).filter(
                    models.Assignment.deleted_at.is_(None),
                    or_(
                        models.Assignment.due_date.is_(None),
                        models.Assignment.due_date >= now,
                    ),
                )
                clean_query = assignment_query.strip()
                for stop_word in ["یک", "یه", "یکی", "تکلیف", "تکالیف", "تکلیفم", "تکلیفمو", "رو", "را"]:
                    clean_query = clean_query.replace(stop_word, "").strip()

                if assignment_query.isdigit():
                    target_assignments = q.filter(models.Assignment.id == int(assignment_query)).all()
                elif clean_query:
                    subj = school_knowledge.resolve_subject(clean_query)
                    s_id = subj["id"] if subj else clean_query
                    s_name = subj["name"] if subj else clean_query
                    target_assignments = q.filter(
                        or_(
                            models.Assignment.title.ilike(f"%{clean_query}%"),
                            models.Assignment.subject_id.ilike(f"%{s_id}%"),
                            models.Assignment.subject_id.ilike(f"%{s_name}%"),
                            models.Assignment.category.ilike(f"%{s_name}%"),
                            models.Assignment.course.ilike(f"%{s_name}%"),
                        )
                    ).all()

                if not target_assignments:
                    # Smart fallback: pick the nearest active pending assignment for this student
                    completed_ids = (
                        select(models.AssignmentCompletion.assignment_id)
                        .filter(models.AssignmentCompletion.user_id == current_user.id)
                    )
                    if action == "complete":
                        fallback_cand = (
                            db.query(models.Assignment)
                            .filter(
                                models.Assignment.deleted_at.is_(None),
                                models.Assignment.is_reminder_only.is_(False),
                                ~models.Assignment.id.in_(completed_ids),
                                or_(
                                    models.Assignment.due_date.is_(None),
                                    models.Assignment.due_date >= now,
                                ),
                            )
                            .order_by(models.Assignment.due_date.asc().nulls_last())
                            .first()
                        )
                    else:
                        fallback_cand = (
                            db.query(models.Assignment)
                            .filter(
                                models.Assignment.deleted_at.is_(None),
                                models.Assignment.id.in_(completed_ids),
                            )
                            .order_by(models.Assignment.updated_at.desc())
                            .first()
                        )

                    if fallback_cand:
                        target_assignments = [fallback_cand]
                    else:
                        return {
                            "success": False,
                            "error": "تکلیف فعال و باقی‌مانده‌ای برای تیک زدن پیدا نشد. همه‌چیز رو انجام دادی! ایول 🔥",
                        }
                target_assignments = target_assignments[:1]

            elif scope == "day":
                resolved_key = None
                if target_day:
                    current_status = school_knowledge.get_current_school_status()
                    if "امروز" in target_day:
                        resolved_key = current_status["day_key"]
                    elif "فردا" in target_day:
                        now_iran = school_knowledge.get_iran_now()
                        tomorrow = now_iran + timedelta(days=1)
                        resolved_key = school_knowledge.WEEKDAYS_MAP.get(tomorrow.weekday(), ("sat", "شنبه"))[0]
                    else:
                        resolved_key = school_knowledge.DAY_LOOKUP.get(target_day)

                all_live = db.query(models.Assignment).filter(
                    models.Assignment.deleted_at.is_(None),
                    or_(
                        models.Assignment.due_date.is_(None),
                        models.Assignment.due_date >= now,
                    )
                ).all()

                for a in all_live:
                    if resolved_key and a.due_date:
                        due_iran = a.due_date + timedelta(hours=3.5)
                        a_key = school_knowledge.WEEKDAYS_MAP.get(due_iran.weekday(), ("", ""))[0]
                        if a_key == resolved_key:
                            target_assignments.append(a)
                    elif resolved_key and not a.due_date:
                        day_sched = school_knowledge.WEEKLY_SCHEDULE.get(resolved_key, {})
                        day_subjs = [p["subject_id"] for p in day_sched.get("periods", [])]
                        if a.subject_id in day_subjs or a.course in day_subjs:
                            target_assignments.append(a)

                # If no assignments found for today (e.g. today is Thursday/Friday), check next school day
                if not target_assignments and ("امروز" in target_day or resolved_key in ("thu", "fri")):
                    current_status = school_knowledge.get_current_school_status()
                    next_key = current_status.get("next_school_key", "sat")
                    for a in all_live:
                        if a.due_date:
                            due_iran = a.due_date + timedelta(hours=3.5)
                            a_key = school_knowledge.WEEKDAYS_MAP.get(due_iran.weekday(), ("", ""))[0]
                            if a_key == next_key:
                                target_assignments.append(a)
                        else:
                            day_sched = school_knowledge.WEEKLY_SCHEDULE.get(next_key, {})
                            day_subjs = [p["subject_id"] for p in day_sched.get("periods", [])]
                            if a.subject_id in day_subjs or a.course in day_subjs:
                                target_assignments.append(a)

                if not target_assignments:
                    day_name = school_knowledge.WEEKLY_SCHEDULE.get(resolved_key, {}).get("day_fa", target_day)
                    return {
                        "success": False,
                        "error": f"هیچ تکلیف فعالی برای روز {day_name} در سیستم پیدا نشد.",
                    }

            elif scope == "all":
                completed_ids = (
                    select(models.AssignmentCompletion.assignment_id)
                    .filter(models.AssignmentCompletion.user_id == current_user.id)
                )
                if action == "complete":
                    target_assignments = (
                        db.query(models.Assignment)
                        .filter(
                            models.Assignment.deleted_at.is_(None),
                            ~models.Assignment.id.in_(completed_ids),
                            or_(
                                models.Assignment.due_date.is_(None),
                                models.Assignment.due_date >= now,
                            ),
                        )
                        .all()
                    )
                else:
                    target_assignments = (
                        db.query(models.Assignment)
                        .filter(
                            models.Assignment.deleted_at.is_(None),
                            models.Assignment.id.in_(completed_ids),
                        )
                        .all()
                    )

            if any(getattr(a, "is_reminder_only", False) for a in target_assignments) and len(target_assignments) == 1:
                return {
                    "success": False,
                    "error": "این تکلیف فقط جهت یادآوری ثبت شده و امکان تیک زدن یا انجام آن وجود ندارد.",
                }
            target_assignments = [a for a in target_assignments if not getattr(a, "is_reminder_only", False)]

            if not target_assignments:
                return {
                    "success": True,
                    "message": "هیچ تکلیفی برای تغییر وضعیت وجود نداشت.",
                    "modified_count": 0,
                }

            from ..routers.assignments import _record_daily_activity
            modified_titles = []
            for a in target_assignments:
                existing = (
                    db.query(models.AssignmentCompletion)
                    .filter(
                        models.AssignmentCompletion.user_id == current_user.id,
                        models.AssignmentCompletion.assignment_id == a.id,
                    )
                    .first()
                )
                if action == "complete":
                    if not existing:
                        db.add(
                            models.AssignmentCompletion(
                                user_id=current_user.id,
                                assignment_id=a.id,
                                completed_at=now,
                            )
                        )
                        _record_daily_activity(db, current_user.id, now, +1)
                        modified_titles.append(a.title)
                else:
                    if existing:
                        db.delete(existing)
                        _record_daily_activity(db, current_user.id, now, -1)
                        modified_titles.append(a.title)

            db.commit()

            entries, _ = build_leaderboard(db)
            user_entry = next((e for e in entries if e["user"].id == current_user.id), None)

            # Trigger Top 1 check in background
            try:
                import asyncio
                from . import telegram_bot
                loop = asyncio.get_running_loop()
                loop.create_task(telegram_bot.check_and_broadcast_top1(db))
            except Exception:
                pass

            act_fa = "انجام شد و تیک خورد" if action == "complete" else "تیک آن برداشته شد"
            return {
                "success": True,
                "action": action,
                "modified_count": len(modified_titles),
                "modified_titles": modified_titles,
                "message": f"تعداد {len(modified_titles)} تکلیف با موفقیت {act_fa}!",
                "new_completion_percentage": round(user_entry.get("completion_percentage", 0), 1) if user_entry else 0,
                "current_streak": user_entry.get("current_streak", 0) if user_entry else 0,
                "new_rank": user_entry.get("rank") if user_entry else "نامشخص",
            }

        elif name == "open_add_homework_wizard":
            if not current_user:
                return {
                    "success": False,
                    "action": "auth_required",
                    "message": "برای افزودن تکلیف باید حساب کاربری شما به ربات متصل باشد.",
                }
            if not (current_user.is_admin or current_user.role in ("admin", "owner")):
                return {
                    "success": False,
                    "action": "permission_denied",
                    "message": f"کاربر {current_user.username}، فقط مدیران و معلمان مدرسه مجاز به افزودن تکلیف جدید هستند.",
                }
            return {
                "success": True,
                "action": "open_wizard",
                "message": "منوی افزودن تکلیف با موفقیت باز شد. کاربر اکنون می‌تواند نوع، درس و مهلت را از طریق دکمه‌ها انتخاب کند.",
            }

        elif name == "render_visual_card":
            from . import card_renderer
            card_type = args.get("card_type", "progress")
            subject = args.get("subject")
            target_day = args.get("target_day")
            image_path, title, summary_data = card_renderer.generate_card(
                db, card_type=card_type, user=current_user, subject=subject, target_day=target_day
            )
            return {
                "success": True,
                "action": "visual_card",
                "card_type": card_type,
                "title": title,
                "image_path": image_path,
                "data_summary": summary_data,
                "message": (
                    f"تصویر کارت گرافیکی '{title}' با موفقیت تولید و ارسال شد. اکنون یک تحلیل انگیزشی و خودمانی در ۲ الی ۳ خط "
                    f"درباره این وضعیت بنویس. فقط متن خالص تحلیلی بنویس و هرگز نام فایل، پسوند .png یا مسیرهای فنی مثل app/ را ننویس."
                ),
            }

        return {"success": False, "error": f"ابزار ناشناخته: {name}"}
    except Exception as exc:
        logger.error("Error executing tool %s: %s", name, exc)
        return {"success": False, "error": str(exc)}


def _is_busy_error(status_code: int, raw_text: str = "") -> bool:
    """Check if the response corresponds to server busy, rate limit, temporary WAF challenge or overload."""
    if status_code in (429, 500, 502, 503, 504):
        return True
    lower = (raw_text or "").lower()
    if status_code == 403 and any(k in lower for k in ("robot.png", "unusual traffic", "automated queries", "captcha", "forbidden")):
        return True
    return any(k in lower for k in ("rate limit", "resource exhausted", "overloaded", "busy", "too many requests", "capacity", "retry"))


def _format_friendly_ai_error(status_code: int, raw_text: str = "") -> str:
    """Generate clear, precise Persian error messages explaining exactly what happened."""
    lower = (raw_text or "").lower()

    # 1. Invalid API Key
    if status_code == 401 or any(k in lower for k in ("invalid api key", "unauthorized", "invalid_api_key", "incorrect api key")):
        return "⚠️ کلید دسترسی (API Key) هوش مصنوعی نامعتبر است یا منقضی شده است. لطفاً کلید API را در تب تنظیمات هوش مصنوعی بررسی کنید."

    # 2. Payment Required / Depleted Credits / Quota
    if status_code == 402 or any(k in lower for k in ("insufficient_quota", "credit", "payment required", "out of credits", "insufficient credits")):
        return "⚠️ اعتبار مالی (Credit) حساب هوش مصنوعی شما در سرویس‌دهنده به پایان رسیده است. لطفاً موجودی حساب خود را در سایت ارائه‌دهنده شارژ کنید."

    # 3. Model not found
    if status_code == 404 or any(k in lower for k in ("model_not_found", "does not exist", "not found")):
        return "⚠️ مدل هوش مصنوعی انتخاب‌شده در این سرویس پیدا نشد یا نام آن اشتباه است. لطفاً نام مدل را در پنل بررسی کنید."

    # 4. Rate limit
    if status_code == 429 or any(k in lower for k in ("rate limit", "too many requests")):
        return "⚠️ محدودیت تعداد درخواست در دقیقه (Rate Limit) برای این مدل پر شده است. لطفاً چند لحظه صبر کرده و دوباره پیام دهید."

    # 5. Unsupported tools / Bad Request
    if status_code == 400:
        if any(k in lower for k in ("tool", "function", "tool_choice")):
            return "⚠️ این مدل هوش مصنوعی از ابزارهای پیشرفته (Tools) پشتیبانی نمی‌کند. لطفاً مدلی هوشمندتر مانند gpt-4o-mini انتخاب کنید."
        return "⚠️ پارامترهای ارسالی به مدل هوش مصنوعی نامعتبر است (خطای ۴۰۰)."

    # 6. Timeout
    if status_code == 504 or "timeout" in lower:
        return "⚠️ مهلت ارتباط با سرور هوش مصنوعی به پایان رسید (Timeout). لطفاً مجدداً امتحان کنید."

    # 7. Server overloaded / busy
    if status_code in (500, 502, 503) or any(k in lower for k in ("overloaded", "busy", "capacity")):
        return "⚠️ سرور ارائه‌دهنده هوش مصنوعی موقتاً با ترافیک بالا مواجه است. لطفاً چند لحظه دیگر پیام دهید."

    # 8. Google / Provider Anti-bot WAF block (403)
    if status_code == 403:
        if any(k in lower for k in ("robot.png", "automated queries", "unusual traffic")):
            return "⚠️ سرویس گوگل موقتاً به دلیل ارسال سریع درخواست‌ها محدودیت اعمال کرده است (Google WAF 403). چند لحظه دیگر امتحان فرمایید."
        return "⚠️ دسترسی به این سرویس یا مدل مجاز نیست (خطای ۴۰۳ Forbidden)."

    return "⚠️ در برقراری ارتباط با مدل هوش مصنوعی خطایی رخ داد. لطفاً تنظیمات کلید و نام مدل را در پنل مدرسه بررسی کنید."


def _handle_ai_error(
    status_code: int,
    raw_text: str,
    current_user: Optional[models.User],
    endpoint_url: str,
    model_name: str,
) -> str:
    """Dispatches full raw error details to Owner PV and returns full log if current user is Owner."""
    from . import telegram_bot
    telegram_bot.dispatch_background_owner_error(
        exc=f"AI Provider HTTP {status_code}: {(raw_text or '')[:300]}",
        endpoint=f"POST {endpoint_url} (model: {model_name})",
        user_info=f"{current_user.username} (ID: {current_user.id})" if current_user else "سیستم / ناشناس",
        raw_response=raw_text,
        status_code=status_code,
    )
    if current_user and models.is_owner(current_user):
        clean_raw = (raw_text or "").strip().replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")[:1500]
        now_str = (datetime.utcnow() + timedelta(hours=3.5)).strftime("%H:%M:%S")
        return (
            f"🚨 <b>لاگ کامل خطای سرویس هوش مصنوعی (Owner Debug Log)</b>\n\n"
            f"📍 <b>سرویس و مدل:</b> <code>{model_name}</code>\n"
            f"🌐 <b>اندپوینت:</b> <code>{endpoint_url}</code>\n"
            f"⚠️ <b>کد وضعیت:</b> <code>HTTP {status_code}</code> ({now_str})\n\n"
            f"📄 <b>پاسخ خام سرویس‌دهنده (Raw Response):</b>\n"
            f"<pre><code class=\"language-json\">{clean_raw}</code></pre>\n\n"
            f"💡 <i>به دلیل دسترسی مدیریت ارشد (Owner)، لاگ فنی کامل به جای متن ساده برای شما ارسال شد.</i>"
        )
    return _format_friendly_ai_error(status_code, raw_text)



def build_live_school_context(db: Session, current_user: Optional[models.User] = None) -> str:
    """Build rich in-memory context containing teachers, schedule, live leaderboard, and active assignments."""
    lines = []
    lines.append(school_knowledge.get_school_knowledge_prompt())
    status = school_knowledge.get_current_school_status()
    lines.append(f"امروز: {status['today_fa']} | ساعت رسمی: {status['current_time']}")

    # Live Leaderboard injected into memory
    try:
        entries, _ = build_leaderboard(db)
        if entries:
            lines.append("\n🏆 جدول رتبه‌بندی زنده کلاس (لیدربورد):")
            for e in entries[:5]:
                u = e["user"]
                r = e.get("rank")
                pct = round(e.get("completion_percentage", 0), 1)
                st = e.get("current_streak", 0)
                lines.append(f"- رتبه {r}: {u.username} (موفقیت: {pct}٪ | استریک: {st} روز)")
        else:
            lines.append("\n🏆 جدول لیدربورد: هنوز رکوردی در کلاس ثبت نشده است.")
    except Exception as exc:
        logger.warning("Could not build leaderboard context: %s", exc)

    # Active & Current Assignments injected into memory (Strictly non-overdue)
    try:
        raw_tasks = (
            db.query(models.Assignment)
            .filter(models.Assignment.deleted_at.is_(None))
            .order_by(models.Assignment.due_date.asc().nulls_last())
            .all()
        )
        active_tasks = [
            t for t in raw_tasks
            if not school_knowledge.is_assignment_overdue(t.due_date, t.subject_id)
        ]

        if current_user:
            completed_ids = set(
                r[0] for r in db.query(models.AssignmentCompletion.assignment_id)
                .filter(models.AssignmentCompletion.user_id == current_user.id)
                .all()
            )
            done_tasks = [t for t in active_tasks if t.id in completed_ids]
            pending_tasks = [t for t in active_tasks if t.id not in completed_ids]

            lines.append(f"\n📝 وضعیت لحظه‌ای تکالیف جاری کاربر ({current_user.username}):")
            if pending_tasks:
                lines.append("⏳ تکالیف جاری باقی‌مانده (تیک‌نخورده / هنوز انجام نشده):")
                for t in pending_tasks:
                    due_str = school_knowledge.format_due_date_relative(t.due_date) if t.due_date else "بدون مهلت خاص"
                    rem = " [فقط جهت یادآوری]" if getattr(t, "is_reminder_only", False) else ""
                    lines.append(f"  ▫️ [شناسه: {t.id}] {t.title} ({t.course or 'عمومی'}) - مهلت: {due_str}{rem}")
            else:
                lines.append("⏳ تکالیف باقی‌مانده: کاربر تمام تکالیف جاری را تیک زده و هیچ تکلیف باقی‌مانده‌ای ندارد! 🎉")

            if done_tasks:
                lines.append("✅ تکالیف جاری انجام‌شده کاربر (تیک‌خورده / حل شده):")
                for t in done_tasks:
                    lines.append(f"  ▫️ [شناسه: {t.id}] {t.title} ({t.course or 'عمومی'}) [انجام شد]")
        else:
            if active_tasks:
                lines.append("\n📝 لیست تکالیف جاری و فعال کلاس:")
                for t in active_tasks:
                    due_str = school_knowledge.format_due_date_relative(t.due_date) if t.due_date else "بدون مهلت خاص"
                    rem = " [فقط جهت یادآوری]" if getattr(t, "is_reminder_only", False) else ""
                    comp_count = db.query(models.AssignmentCompletion).filter(models.AssignmentCompletion.assignment_id == t.id).count()
                    lines.append(f"  ▫️ [شناسه: {t.id}] {t.title} ({t.course or 'عمومی'}) - مهلت: {due_str}{rem} (انجام داده: {comp_count} نفر)")
            else:
                lines.append("\n📝 لیست تکالیف: در حال حاضر هیچ تکلیف فعال و جاری در کلاس ثبت نشده است.")

        lines.append(
            "\n⛔ قانون حیاتی عدم اشاره به تکالیف منقضی‌شده:\n"
            "تکالیفی که مهلت آن‌ها سپری شده است (Overdue)، کاملاً از دسترس شما خارج شده‌اند و نباید به عنوان تکلیف جاری شناخته شوند. هرگز در پاسخ‌های خود به تکالیف گذشته یا منقضی‌شده اشاره نکن. فقط تکالیفی که در بالا لیست شده‌اند تکالیف جاری و فعال هستند."
        )

        lines.append(
            "\n🎨 دستور حیاتی نمودارها و گرافیک: هر زمان کاربر خواستار دیدن نمودار، کارنامه تصویری، چارت پیشرفت، عکس برنامه یا گفت «نمودار درست کن»، موظف هستی بلافاصله ابزار render_visual_card را فراخوانی کنی."
        )
    except Exception as exc:
        logger.warning("Could not build assignments context: %s", exc)

    return "\n".join(lines)


async def ask_universal_ai_agent(
    user_prompt: str,
    api_key: str,
    db: Session,
    base_url: str = "https://openrouter.ai/api/v1",
    model_name: str = "openai/gpt-4o-mini",
    current_user: Optional[models.User] = None,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    is_recent: bool = False,
) -> Tuple[str, Dict[str, Any]]:
    """Universal OpenAI-compatible chat completions caller with Tools / Function Calling.

    Works natively with OpenRouter, Grok (xAI), DeepSeek, OpenAI, Groq, Together, and self-hosted models.
    """
    meta: Dict[str, Any] = {"open_wizard": False}
    if not api_key:
        return ("⚠️ کلید API هوش مصنوعی هنوز در پنل مدیریت مدرسه تنظیم نشده است.", meta)

    clean_base = (base_url or "https://openrouter.ai/api/v1").rstrip("/")
    if not clean_base.endswith("/chat/completions"):
        endpoint_url = f"{clean_base}/chat/completions"
    else:
        endpoint_url = clean_base

    # Target Google Gemini directly via Cloudflare WARP IPv6
    is_gemini = "generativelanguage.googleapis.com" in endpoint_url or "googleapis.com" in endpoint_url or "gemini" in clean_model.lower()
    if "archschool.vidxsepehr.ir/gemini" in endpoint_url:
        endpoint_url = endpoint_url.replace(
            "https://archschool.vidxsepehr.ir/gemini",
            "https://generativelanguage.googleapis.com",
        )

    clean_model = model_name.strip() if model_name else "openai/gpt-4o-mini"

    prompts_cfg = get_ai_prompts_and_config(db)

    messages: List[Dict[str, Any]] = []

    # Assemble unified system instruction (Custom prompt + Persona anchor + Live school context)
    system_sections: List[str] = []
    if prompts_cfg.get("system_prompt") and prompts_cfg["system_prompt"].strip():
        system_sections.append(prompts_cfg["system_prompt"].strip())

    if prompts_cfg.get("persona_anchor") and prompts_cfg["persona_anchor"].strip():
        system_sections.append(prompts_cfg["persona_anchor"].strip())

    live_context = build_live_school_context(db, current_user)
    if live_context and live_context.strip():
        system_sections.append(f"اطلاعات زنده پایگاه داده مدرسه:\n{live_context.strip()}")

    if system_sections:
        messages.append({"role": "system", "content": "\n\n".join(system_sections)})

    # Conversation history
    if conversation_history:
        messages.extend(conversation_history)

    # User prompt
    user_meta = f"کاربر: {current_user.username} (نقش: {current_user.role})" if current_user else "کاربر: ناشناس"
    messages.append({
        "role": "user",
        "content": f"[{user_meta}]\n{user_prompt}",
    })

    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    }
    if "openrouter.ai" in endpoint_url:
        headers["HTTP-Referer"] = "https://archschool.vidxsepehr.ir"
        headers["X-Title"] = "ArchSchool Assistant"

    payload: Dict[str, Any] = {
        "model": clean_model,
        "messages": messages,
        "tools": OPENAI_TOOLS,
        "tool_choice": "auto",
        "temperature": prompts_cfg.get("temperature", 0.7),
        "max_tokens": prompts_cfg.get("max_tokens", 1000),
    }

    try:
        use_warp = is_gemini and (get_warp_proxy_url() is not None)
        client = get_warp_client() if use_warp else get_shared_client()
        resp = None
        last_status = 200
        last_text = ""

        for attempt in range(1, 4):
            try:
                resp = await client.post(endpoint_url, json=payload, headers=headers)
                if resp.status_code == 200:
                    break
                last_status = resp.status_code
                last_text = resp.text
                logger.warning(
                    "AI provider busy/error (attempt %d/3) %s from %s: %s",
                    attempt, resp.status_code, endpoint_url, resp.text[:200]
                )
                if attempt < 3 and _is_busy_error(resp.status_code, resp.text):
                    await asyncio.sleep(2.0)
                    continue
                break
            except (httpx.ProxyError, httpx.ConnectError, httpx.ConnectTimeout) as proxy_err:
                if use_warp:
                    logger.warning("Cloudflare WARP proxy unreachable (%s). Retrying direct...", proxy_err)
                    use_warp = False
                    client = get_shared_client()
                    continue
                logger.warning("AI provider connection error (attempt %d/3): %s", attempt, proxy_err)
                if attempt < 3:
                    await asyncio.sleep(2.0)
                    continue
                return (_format_friendly_ai_error(504, "Connection error"), meta)
            except (httpx.TimeoutException, httpx.NetworkError) as net_err:
                logger.warning("AI provider network/timeout (attempt %d/3): %s", attempt, net_err)
                if attempt < 3:
                    await asyncio.sleep(2.0)
                    continue
                return (_format_friendly_ai_error(504, "Network timeout"), meta)

        # Automatic fallback for models that don't support tools/function calling (HTTP 400)
        if resp is not None and resp.status_code == 400 and "tools" in payload:
            lower_err = (resp.text or "").lower()
            if any(k in lower_err for k in ("tool", "function", "unsupported", "unexpected argument", "additional properties")):
                logger.warning("Model '%s' does not support tools parameter. Retrying as plain completion...", clean_model)
                payload_no_tools = {k: v for k, v in payload.items() if k not in ("tools", "tool_choice")}
                try:
                    resp = await client.post(endpoint_url, json=payload_no_tools, headers=headers)
                    if resp.status_code == 200:
                        last_status = 200
                except Exception as fb_err:
                    logger.warning("Fallback without tools failed: %s", fb_err)

        if not resp or resp.status_code != 200:
            logger.error("AI provider error %s after retries from %s: %s", last_status, endpoint_url, last_text)
            return (_handle_ai_error(last_status, last_text, current_user, endpoint_url, clean_model), meta)

        data = resp.json()
        choices = data.get("choices", [])
        if not choices:
            return ("پاسخی از هوش مصنوعی دریافت نشد.", meta)

        first_choice = choices[0]
        choice_message = first_choice.get("message", {})
        tool_calls = choice_message.get("tool_calls")

        # --- Tool Calling Branch ---
        if tool_calls:
            clean_assistant: Dict[str, Any] = {
                "role": "assistant",
                "content": choice_message.get("content"),
                "tool_calls": tool_calls,
            }
            messages.append(clean_assistant)

            last_fn_name = ""
            last_tool_output: Dict[str, Any] = {}
            last_fn_args: Dict[str, Any] = {}

            for tc in tool_calls:
                call_id = tc.get("id") or "call_1"
                fn_data = tc.get("function", {})
                fn_name = fn_data.get("name", "")
                fn_args_raw = fn_data.get("arguments", "{}")
                try:
                    fn_args = json.loads(fn_args_raw) if isinstance(fn_args_raw, str) else fn_args_raw
                except Exception:
                    fn_args = {}

                last_fn_name = fn_name
                last_fn_args = fn_args

                logger.info("Universal AI invoking tool: %s with args: %s", fn_name, fn_args)
                tool_output = execute_tool(fn_name, fn_args, db, current_user)
                last_tool_output = tool_output

                if fn_name == "open_add_homework_wizard" and tool_output.get("success"):
                    meta["open_wizard"] = True
                if fn_name == "render_visual_card" and tool_output.get("success"):
                    meta["visual_card"] = {
                        "card_type": tool_output.get("card_type"),
                        "title": tool_output.get("title"),
                        "image_path": tool_output.get("image_path"),
                    }

                tool_for_llm = dict(tool_output)
                if fn_name == "render_visual_card":
                    tool_for_llm.pop("image_path", None)

                messages.append({
                    "role": "tool",
                    "tool_call_id": str(call_id),
                    "content": json.dumps(tool_for_llm, ensure_ascii=False),
                })

            # Check if wizard tool was opened
            if last_fn_name == "open_add_homework_wizard":
                if last_tool_output.get("success"):
                    meta["open_wizard"] = True
                    return ("منوی افزودن تکلیف جدید باز شد. لطفاً نوع، موضوع و مهلت را از گزینه‌های زیر انتخاب کنید:", meta)
                else:
                    err_msg = last_tool_output.get("message") or "دسترسی لازم برای افزودن تکلیف وجود ندارد."
                    return (err_msg, meta)

            if len(tool_calls) == 1 and last_fn_name == "toggle_assignment_completion":
                if last_tool_output.get("success"):
                    titles = "، ".join(last_tool_output.get("modified_titles", [])) or "تکلیف"
                    act = last_tool_output.get("action", "complete")
                    streak = last_tool_output.get("current_streak", 0)
                    pct = last_tool_output.get("new_completion_percentage", 0)
                    if act == "complete":
                        return (f"تکلیف «{titles}» با موفقیت به عنوان انجام‌شده ثبت شد. (استریک: {streak} روز | موفقیت کل: {pct}٪)", meta)
                    else:
                        return (f"علامت انجام تکلیف «{titles}» برداشته شد.", meta)
                else:
                    err = last_tool_output.get("error") or last_tool_output.get("message") or "تکلیفی برای تغییر پیدا نشد."
                    return (err, meta)

            # Fast follow-up request for read-only queries (schedule, status, leaderboard)
            if prompts_cfg.get("followup_anchor"):
                messages.append({
                    "role": "user",
                    "content": f"[دستور لحن و تحلیل خروجی ابزار]\n{prompts_cfg['followup_anchor']}",
                })
            followup_payload = {
                "model": clean_model,
                "messages": messages,
                "temperature": prompts_cfg.get("temperature", 0.7),
                "max_tokens": prompts_cfg.get("max_tokens", 1000),
            }
            followup_resp = None
            for f_attempt in range(1, 4):
                try:
                    followup_resp = await client.post(endpoint_url, json=followup_payload, headers=headers)
                    if followup_resp.status_code == 200:
                        break
                    if f_attempt < 3 and _is_busy_error(followup_resp.status_code, followup_resp.text):
                        await asyncio.sleep(2.0)
                        continue
                    break
                except (httpx.ProxyError, httpx.ConnectError, httpx.ConnectTimeout):
                    client = get_shared_client()
                    if f_attempt < 3:
                        await asyncio.sleep(2.0)
                        continue
                    break
                except (httpx.TimeoutException, httpx.NetworkError):
                    if f_attempt < 3:
                        await asyncio.sleep(2.0)
                        continue
                    break

            if followup_resp and followup_resp.status_code == 200:
                followup_data = followup_resp.json()
                followup_choices = followup_data.get("choices", [])
                if followup_choices:
                    final_content = followup_choices[0].get("message", {}).get("content", "")
                    return (final_content or "انجام شد.", meta)

            # --- Resilient Fallback for Successful Tools ---
            # If the tool succeeded but turn 2 (AI commentary) failed due to rate-limit/WAF 403:
            if last_tool_output.get("success"):
                if last_fn_name == "render_visual_card":
                    return ("گزارش و نمودار تحلیلی وضعیت شما با موفقیت آماده شد.", meta)
                if last_fn_name == "get_my_status":
                    u_name = current_user.username if current_user else "دانش‌آموز"
                    pct = last_tool_output.get("completion_percentage", 0)
                    st = last_tool_output.get("current_streak", 0)
                    rk = last_tool_output.get("rank", "-")
                    return (f"📊 <b>وضعیت تحصیلی {u_name}:</b>\n🔥 استریک: <b>{st} روز</b>\n📈 درصد تکمیل تکالیف: <b>{pct}٪</b>\n🏆 رتبه کلاسی: <b>رتبه {rk}</b>", meta)
                if last_fn_name == "get_class_leaderboard":
                    lb_list = last_tool_output.get("leaderboard", [])
                    lb_lines = [f"{e.get('rank')}. <b>{e.get('username')}</b> ({e.get('completion_percentage', 0)}٪)" for e in lb_list[:5]]
                    return ("🏆 <b>جدول رتبه‌بندی برتر کلاس:</b>\n" + ("\n".join(lb_lines) if lb_lines else "اطلاعاتی ثبت نشده است."), meta)
                if last_fn_name == "get_weekly_schedule":
                    sched_desc = last_tool_output.get("current_status", {}).get("status_text", "برنامه کلاسی هفتگی")
                    return (f"📅 <b>برنامه کلاسی:</b> {sched_desc}", meta)
                if last_fn_name == "toggle_assignment_completion":
                    return (last_tool_output.get("message") or "تغییر وضعیت تکلیف با موفقیت انجام شد.", meta)

            if followup_resp:
                return (_handle_ai_error(followup_resp.status_code, followup_resp.text, current_user, endpoint_url, clean_model), meta)

        # Normal text content
        content = choice_message.get("content", "")
        import re
        if content and "[" in content and "]" in content:
            bracket_match = re.search(r"\[(get_[a-zA-Z0-9_]+|open_add_homework_wizard|toggle_[a-zA-Z0-9_]+|render_visual_card)\]", content)
            if bracket_match:
                pseudo_fn = bracket_match.group(1)
                logger.info("Executing text-bracketed tool fallback: %s", pseudo_fn)
                res = execute_tool(pseudo_fn, {"card_type": "progress"} if pseudo_fn == "render_visual_card" else {}, db, current_user)
                if pseudo_fn == "open_add_homework_wizard" and res.get("success"):
                    meta["open_wizard"] = True
                    return ("منوی افزودن تکلیف جدید باز شد. لطفاً نوع، موضوع و مهلت را از گزینه‌های زیر انتخاب کنید:", meta)
                if pseudo_fn == "render_visual_card" and res.get("success"):
                    meta["visual_card"] = {
                        "card_type": res.get("card_type"),
                        "title": res.get("title"),
                        "image_path": res.get("image_path"),
                    }
                cleaned_content = re.sub(r"\[(get_[a-zA-Z0-9_]+|open_add_homework_wizard|toggle_[a-zA-Z0-9_]+|render_visual_card)\]", "", content).strip()
                followup_messages = list(messages)
                followup_messages.append({"role": "assistant", "content": cleaned_content or f"در حال اجرای {pseudo_fn}"})
                followup_messages.append({"role": "user", "content": f"نتیجه واقعی از دیتابیس:\n{json.dumps(res, ensure_ascii=False)}"})
                if prompts_cfg.get("followup_anchor"):
                    followup_messages.append({
                        "role": "system",
                        "content": prompts_cfg["followup_anchor"],
                    })
                try:
                    f_resp = await client.post(endpoint_url, json={"model": clean_model, "messages": followup_messages, "max_tokens": prompts_cfg.get("max_tokens", 1000), "temperature": prompts_cfg.get("temperature", 0.7)}, headers=headers)
                    if f_resp.status_code == 200:
                        f_choices = f_resp.json().get("choices", [])
                        if f_choices:
                            return (f_choices[0].get("message", {}).get("content", ""), meta)
                except Exception as b_err:
                    logger.warning("Error in bracket fallback: %s", b_err)

        return (content or "متوجه پیامت نشدم، لطفاً دوباره بگو!", meta)

    except httpx.TimeoutException:
        logger.error("AI provider timeout to %s", endpoint_url)
        return (_handle_ai_error(504, "Connection timed out after 3 retries", current_user, endpoint_url, clean_model), meta)
    except Exception as exc:
        logger.error("Universal AI agent exception: %s", exc, exc_info=True)
        return (_handle_ai_error(500, f"{type(exc).__name__}: {str(exc)}", current_user, endpoint_url, clean_model), meta)


async def generate_ai_event_text(
    db: Session,
    event_type: str,
    context_data: Dict[str, Any],
) -> str:
    """Generate dynamic AI-crafted announcement or follow-up text for automated events.

    Uses the user's configured event prompt from the Admin panel. Falls back gracefully
    if AI is unavailable or produces an error.
    """
    from . import telegram_bot
    from ..prompts import default_prompts

    prompt_key = f"notify_{event_type}_prompt"
    def_prompt_attr = f"DEFAULT_NOTIFY_{event_type.upper()}_PROMPT"
    default_prompt = getattr(default_prompts, def_prompt_attr, "")
    event_prompt = telegram_bot.get_bot_setting(db, prompt_key, default_prompt)

    api_key = telegram_bot.get_bot_setting(db, "ai_api_key") or telegram_bot.get_bot_setting(db, "gemini_api_key")
    if not api_key:
        return ""

    provider = telegram_bot.get_bot_setting(db, "ai_provider", "openrouter")
    def_base, def_model = telegram_bot.get_provider_defaults(provider)
    base_url = telegram_bot.get_bot_setting(db, "ai_base_url") or def_base
    model_name = telegram_bot.get_bot_setting(db, "ai_model") or def_model

    endpoint_url = base_url.rstrip("/")
    if not endpoint_url.endswith("/chat/completions"):
        endpoint_url = f"{endpoint_url}/chat/completions"

    clean_model = model_name.strip()
    if clean_model.startswith("models/"):
        clean_model = clean_model[len("models/"):]

    persona = (
        telegram_bot.get_bot_setting(db, "ai_persona_anchor")
        or telegram_bot.get_bot_setting(db, "ai_system_prompt")
        or "تو هوش مصنوعی و ربات هوشمند کلاس درس ArchSchool هستی."
    )

    sys_instr = (
        f"{persona}\n\n"
        f"دستورالعمل ویژه این رویداد:\n{event_prompt}\n\n"
        f"قوانین مهم نگارش تلگرام:\n"
        f"۱. مستقیماً متن نهایی پیام تلگرام را به فارسی روان و جذاب خروجی بده (بدون هرگونه پیش‌درآمد یا کلمات اضافه).\n"
        f"۲. از تگ‌های استاندارد HTML تلگرام (<b>، <i>، <code>) استفاده کن.\n"
        f"۳. در صورتی که شناسه کاربری تلگرام یا منشن (@username یا تگ کاربری) در داده‌های رویداد آمده است، حتماً آن را دقیقاً در متن درج کن تا کاربر نوتیفیکیشن دریافت کند.\n"
        f"۴. به هیچ وجه نام فایل‌ها، فرمت‌های برنامه‌نویسی یا مسیرهای فنی سرور را ننویس."
    )

    user_msg = f"اطلاعات رویداد:\n{json.dumps(context_data, ensure_ascii=False, indent=2)}"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if "openrouter" in endpoint_url.lower():
        headers["HTTP-Referer"] = "https://archschool.vidxsepehr.ir"
        headers["X-Title"] = "ArchSchool"

    payload = {
        "model": clean_model,
        "messages": [
            {"role": "system", "content": sys_instr},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.85,
        "max_tokens": 600,
    }

    client = get_shared_client()
    for attempt in range(1, 3):
        try:
            resp = await client.post(endpoint_url, json=payload, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                choices = data.get("choices", [])
                if choices:
                    text = choices[0].get("message", {}).get("content", "").strip()
                    if text:
                        return text
            if attempt < 2 and _is_busy_error(resp.status_code, resp.text):
                await asyncio.sleep(2.0)
                continue
            break
        except Exception as exc:
            logger.warning("generate_ai_event_text attempt %s failed: %s", attempt, exc)
            if attempt < 2:
                await asyncio.sleep(2.0)
                continue
            break

    return ""

