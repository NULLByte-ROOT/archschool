import asyncio
import json
import logging
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


def get_shared_client() -> httpx.AsyncClient:
    """Persistent connection pool to prevent per-request TLS handshake and TCP latency."""
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.AsyncClient(
            timeout=30.0,
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=50, keepalive_expiry=60.0),
        )
    return _shared_client

_prompt_cache: Optional[Dict[str, Any]] = None
_prompt_cache_time: float = 0.0


def invalidate_prompt_cache() -> None:
    """Invalidate cached prompts so updates in admin panel take effect immediately."""
    global _prompt_cache, _prompt_cache_time
    _prompt_cache = None
    _prompt_cache_time = 0.0


def get_ai_prompts_and_config(db: Session) -> Dict[str, Any]:
    """Retrieve system instruction, anchors, temperature, and max_tokens from DB (cached for 60s)."""
    global _prompt_cache, _prompt_cache_time
    import time
    now = time.time()
    if _prompt_cache is not None and (now - _prompt_cache_time) < 60.0:
        return _prompt_cache

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

    _prompt_cache = {
        "system_prompt": system_prompt,
        "persona_anchor": persona_anchor,
        "followup_anchor": followup_anchor,
        "temperature": temp,
        "max_tokens": max_tokens,
    }
    _prompt_cache_time = now
    return _prompt_cache

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
            "description": "دریافت لیست تکالیف فعال و جاری کلاس (تکالیفی که مهلت تحویل آن‌ها هنوز نگذشته است) با قابلیت فیلتر بر اساس درس",
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
                    "include_expired": {
                        "type": "boolean",
                        "description": "آیا تکالیف قدیمی و منقضی‌شده قبلی هم آورده شوند؟ پیش‌فرض false است و فقط تکالیف معتبر و فعال می‌آیند.",
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
            "name": "open_add_homework_wizard",
            "description": "باز کردن و ارسال منوی تعاملی و دکمه‌ای هوشمند برای افزودن یا ثبت تکلیف، مشق، امتحان، پروژه یا یادآوری جدید در مدرسه. هر زمان کاربر تمایل به ایجاد، ثبت، تعریف، یا افزودن تکلیف یا یادآوری جدید داشت، این ابزار را فراخوانی کن.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
]


def execute_tool(
    name: str, args: Dict[str, Any], db: Session, current_user: Optional[models.User]
) -> Dict[str, Any]:
    """Execute python functions corresponding to function calls."""
    try:
        if name == "get_my_status":
            if not current_user:
                return {
                    "success": False,
                    "message": "اکانت تلگرام شما هنوز به حساب کاربری ArchSchool لینک نشده است. لطفاً کد اتصال اختصاصی خود را از تب پروفایل اپلیکیشن کپی کرده و در پیوی ربات بفرستید تا حساب شما متصل شود.",
                }

            entries, _ = build_leaderboard(db)
            user_entry = next((e for e in entries if e["user"].id == current_user.id), None)
            now = datetime.utcnow()

            # Find uncompleted assignments that are currently ACTIVE (deadline not expired or no deadline)
            completed_ids = (
                select(models.AssignmentCompletion.assignment_id)
                .filter(models.AssignmentCompletion.user_id == current_user.id)
            )
            pending = (
                db.query(models.Assignment)
                .filter(
                    models.Assignment.deleted_at.is_(None),
                    ~models.Assignment.id.in_(completed_ids),
                    or_(
                        models.Assignment.due_date.is_(None),
                        models.Assignment.due_date >= now,
                    ),
                )
                .order_by(
                    models.Assignment.due_date.asc().nulls_last(),
                    models.Assignment.created_at.desc(),
                )
                .limit(5)
                .all()
            )

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
            include_expired = args.get("include_expired", False)
            subject_filter = args.get("subject", "").strip()
            now = datetime.utcnow()

            query = db.query(models.Assignment).filter(models.Assignment.deleted_at.is_(None))

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

            if not include_expired:
                # ONLY active assignments whose deadline has not passed (or have no deadline)
                query = query.filter(
                    or_(
                        models.Assignment.due_date.is_(None),
                        models.Assignment.due_date >= now,
                    )
                )
                query = query.order_by(
                    models.Assignment.due_date.asc().nulls_last(),
                    models.Assignment.created_at.desc(),
                )
            else:
                query = query.order_by(models.Assignment.created_at.desc())

            assignments = query.limit(limit).all()

            if not assignments:
                msg = f"در حال حاضر هیچ تکلیف فعالی برای درس '{subject_filter}' وجود ندارد." if subject_filter else "در حال حاضر هیچ تکلیف فعالی با مهلت تحویل باز در سامانه وجود ندارد."
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
                    "is_expired": bool(a.due_date and a.due_date < now),
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
                    "error": "عدم دسترسی! در سامانه ArchSchool فقط ادمین یا مالک مدرسه مجاز به ثبت تکلیف جدید هستند.",
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
                "message": f"تکلیف '{title}' با موفقیت توسط {current_user.username} در سامانه ثبت شد و امتیاز فعالیت به شما تعلق گرفت!",
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
                q = db.query(models.Assignment).filter(models.Assignment.deleted_at.is_(None))
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
                                    models.Assignment.due_date >= now - timedelta(days=1),
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
                        models.Assignment.due_date >= now - timedelta(days=2),
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

        return {"success": False, "error": f"ابزار ناشناخته: {name}"}
    except Exception as exc:
        logger.error("Error executing tool %s: %s", name, exc)
        return {"success": False, "error": str(exc)}


def _is_busy_error(status_code: int, raw_text: str = "") -> bool:
    """Check if the response corresponds to server busy, rate limit, quota exhaustion or temporary overload."""
    if status_code in (429, 500, 502, 503, 504):
        return True
    lower = raw_text.lower()
    return any(k in lower for k in ("rate limit", "resource exhausted", "overloaded", "busy", "quota", "too many requests", "capacity", "retry"))


def _format_friendly_ai_error(status_code: int, raw_text: str) -> str:
    """Generate friendly Persian error messages without exposing technical codes or raw HTML/JSON."""
    return "در ارتباط با هوش مصنوعی مشکلی پیش آمد. لطفاً ۱ دقیقه دیگر دوباره تلاش کنید."



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

    # Active Assignments injected into memory
    try:
        now = datetime.now(timezone.utc)
        active_tasks = (
            db.query(models.Assignment)
            .filter(models.Assignment.deleted_at.is_(None))
            .order_by(models.Assignment.due_date.asc().nulls_last())
            .all()
        )
        if active_tasks:
            lines.append("\n📝 لیست تکالیف فعال در سامانه:")
            for t in active_tasks:
                due_str = t.due_date.strftime("%Y-%m-%d %H:%M") if t.due_date else "بدون مهلت خاص"
                rem = " [فقط جهت یادآوری]" if getattr(t, "is_reminder_only", False) else ""
                lines.append(f"- {t.title} ({t.course or 'عمومی'}) - مهلت: {due_str}{rem}")
        else:
            lines.append("\n📝 لیست تکالیف: در حال حاضر هیچ تکلیف فعالی در سامانه ثبت نشده است.")
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

    # Route Google Gemini through host IPv6 gateway to bypass Contabo IPv4 blacklist
    if "generativelanguage.googleapis.com" in endpoint_url:
        endpoint_url = endpoint_url.replace(
            "https://generativelanguage.googleapis.com",
            "https://archschool.vidxsepehr.ir/gemini",
        )

    clean_model = model_name.strip() if model_name else "openai/gpt-4o-mini"

    prompts_cfg = get_ai_prompts_and_config(db)

    messages: List[Dict[str, Any]] = []

    # 1. Custom System Instruction (if set in admin panel)
    if prompts_cfg.get("system_prompt"):
        messages.append({"role": "system", "content": prompts_cfg["system_prompt"]})

    # 2. In-Memory School Database Context (factual data: teachers, schedule, active tasks, leaderboard)
    live_context = build_live_school_context(db, current_user)
    if live_context:
        messages.append({
            "role": "system",
            "content": f"اطلاعات زنده پایگاه داده مدرسه:\n{live_context}",
        })

    # 3. Conversation history
    if conversation_history:
        messages.extend(conversation_history)

    # 4. Persona anchor (if set in admin panel)
    if prompts_cfg.get("persona_anchor"):
        messages.append({
            "role": "system",
            "content": prompts_cfg["persona_anchor"],
        })

    # 5. User prompt
    user_meta = f"کاربر: {current_user.username} (نقش: {current_user.role})" if current_user else "کاربر: ناشناس"
    messages.append({
        "role": "user",
        "content": f"[{user_meta}]\n{user_prompt}",
    })

    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json",
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
        client = get_shared_client()
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
            except (httpx.TimeoutException, httpx.NetworkError) as net_err:
                logger.warning("AI provider network/timeout (attempt %d/3): %s", attempt, net_err)
                if attempt < 3:
                    await asyncio.sleep(2.0)
                    continue
                return (_format_friendly_ai_error(504, "Network timeout"), meta)

        if not resp or resp.status_code != 200:
            logger.error("AI provider error %s after retries from %s: %s", last_status, endpoint_url, last_text)
            return (_format_friendly_ai_error(last_status, last_text), meta)

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

                messages.append({
                    "role": "tool",
                    "tool_call_id": str(call_id),
                    "content": json.dumps(tool_output, ensure_ascii=False),
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
                    "role": "system",
                    "content": prompts_cfg["followup_anchor"],
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
            elif followup_resp:
                return (_format_friendly_ai_error(followup_resp.status_code, followup_resp.text), meta)

        # Normal text content
        content = choice_message.get("content", "")
        import re
        if content and "[" in content and "]" in content:
            bracket_match = re.search(r"\[(get_[a-zA-Z0-9_]+|open_add_homework_wizard|toggle_[a-zA-Z0-9_]+)\]", content)
            if bracket_match:
                pseudo_fn = bracket_match.group(1)
                logger.info("Executing text-bracketed tool fallback: %s", pseudo_fn)
                res = execute_tool(pseudo_fn, {}, db, current_user)
                if pseudo_fn == "open_add_homework_wizard" and res.get("success"):
                    meta["open_wizard"] = True
                    return ("منوی افزودن تکلیف جدید باز شد. لطفاً نوع، موضوع و مهلت را از گزینه‌های زیر انتخاب کنید:", meta)
                cleaned_content = re.sub(r"\[(get_[a-zA-Z0-9_]+|open_add_homework_wizard|toggle_[a-zA-Z0-9_]+)\]", "", content).strip()
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
        return (_format_friendly_ai_error(504, "Timeout"), meta)
    except Exception as exc:
        logger.error("Universal AI agent exception: %s", exc)
        return (_format_friendly_ai_error(500, str(exc)), meta)
