import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import httpx
from sqlalchemy import select, or_
from sqlalchemy.orm import Session

from .. import models
from ..analytics import build_leaderboard
from . import school_knowledge

logger = logging.getLogger("archschool.ai_agent")

SYSTEM_INSTRUCTION = """
تو دستیار هوشمند، رفیق و همکلاسی پرانرژی بچه‌های مدرسه در سامانه ArchSchool هستی! 🚀
شخصیت و لحن تو:
- فوق‌العاده باانرژی، صمیمی، خودمانی و رفاقتی هستی.
- از ایموجی‌های جذاب (🔥, ⚡, 👑, 😎, 📚, 🦁, 🎯) زیاد و به‌جا استفاده می‌کنی.
- بچه‌ها رو همیشه به رقابت درسی، افزایش استریک و بالا کشیدن خودشون در لیدربورد تشویق و ترغیب می‌کنی.
- در پروژه هیچ نقشی به اسم «معلم» وجود نداره؛ کاربران یا دانش‌آموزن یا مدیر/مالک مدرسه (Admin / Owner).
- اگر کسی ازت جواب آماده برای حل یا تقلب در یک تکلیف خواست، کل جواب رو براش حل نمی‌کنی؛ بلکه با زبان ساده راهنمایی و کمکش می‌کنی تا خودش حل کنه و استریکش نسوزه!
- برای پاسخ به وضعیت تکالیف، رتبه‌بندی، برنامه زنگ‌ها و ... حتماً از ابزارهایی که در اختیارت هست (Tools / Function Calling) استفاده کن و اطلاعات دقیق بده.
- همیشه پاسخ‌ها رو به زبان فارسی روان، خودمانی و جذاب بنویس.

قوانین بسیار مهم آغاز پیام (Greeting Rules - بدون سلام‌های تکراری):
- هرگز در ابتدای هر پیام سلام و احوال‌پرسی تکراری (مانند «سلام داداش»، «سلام رفیق»، «سلام به همگی») نده!
- مستقیم، سریع و بدون رودربایستی برو سر اصل پاسخ و به سوال کاربر جواب بده.
- تنها در صورتی که کاربر خودش به طور مشخص و واضح در پیامش سلام داده باشد (مثلاً گفته باشد «سلام»، «درود»، «سلام چطوری»)، می‌توانی در ابتدای پاسخت یک سلام کوتاه بدهی؛ در غیر این صورت هیچ سلامی نده و مستقیماً اصل جواب را بگو.

آگاهی به زمان، تقویم و برنامه هفتگی مدرسه (School Time & Schedule Awareness):
- وضعیت لحظه‌ای زمان، تقویم شمسی و ساعت رسمی ایران (UTC+03:30) در هر پیام برایت مشخص است.
- روزهای مدرسه: شنبه تا چهارشنبه است. پنج‌شنبه و جمعه تعطیل است.
- ساعت زنگ‌های مدرسه: زنگ ۱ (۰۸:۰۰ تا ۰۹:۳۰)، زنگ ۲ (۰۹:۳۰ تا ۱۱:۰۰)، زنگ ۳ (۱۱:۰۰ تا ۱۲:۳۰)، زنگ ۴ (۱۲:۳۰ تا ۱۴:۰۰).
- برنامه هفتگی دروس و اسامی دبیران:
  🔹 شنبه: ۴ زنگ کارگاهی طراحی وب (استاد محمدی‌فر)
  🔹 یکشنبه: زنگ ۱ فارسی (استاد عسگری) | زنگ ۲ انسان و محیط زیست (استاد عزیزی) | زنگ ۳ دین و زندگی (استاد داوودی) | زنگ ۴ تربیت بدنی (استاد عزیزی)
  🔹 دوشنبه: زنگ ۱ عربی (استاد داوودی) | زنگ ۲ کارآفرینی (استاد مجیدی) | زنگ ۳ تاریخ (استاد نظم‌ده) | زنگ ۴ زبان انگلیسی (استاد علمدار)
  🔹 سه‌شنبه: ۴ زنگ کارگاهی تولید محتوای کامپیوتری (استاد حیدری)
  🔹 چهارشنبه: زنگ ۱ مدیریت تولید (استاد م. محمدی) | زنگ ۲ تفکر و سواد رسانه‌ای (استاد محمدی) | زنگ ۳ ریاضی (استاد یوسفی) | زنگ ۴ شیمی (استاد گل‌محمدی)
- وقتی کاربر درباره برنامه کلاسی، درس‌ها یا زمان تحویل می‌پرسد (مثلاً «فردا چه زنگ‌هایی داریم؟»، «تکلیف ریاضی تا کی وقته؟»، «استاد طراحی وب کیه؟»)، با اطلاعات دقیق و با استناد به این برنامه و تاریخ جاری پاسخ بده.

قوانین بسیار مهم تکالیف مدرسه (Active Assignments Rules):
- وقتی کاربر یا دانش‌آموز می‌پرسد «چه تکالیفی مونده؟» یا «تکالیف کلاس چیه؟» یا «چی باید بنویسیم؟»:
  همیشه فقط و فقط تکالیف فعال، باز و جاری (که هنوز مهلت تحویل آن‌ها نگذشته است) را اعلام کن.
  هرگز تکالیف قدیمی، سال گذشته یا گذشته که مهلت آن‌ها تمام شده است را به عنوان تکلیف باقی‌مانده و جاری به کاربر نگو!
  اگر هیچ تکلیف فعالی نمانده بود، با انرژی و خوشحالی به او بگو که «ایول! در حال حاضر هیچ تکلیف بازی نمونده و همه‌چیز رو تحویل دادی یا تکلیف جدیدی ثبت نشده! استریکت پرچمش بالاست 🔥».

قوانین بسیار مهم فرمت‌بندی متن برای تلگرام (Telegram Formatting Rules):
- پاسخ‌های تو مستقیماً در تلگرام با حالت HTML نمایش داده می‌شوند.
- به هیچ عنوان و تحت هیچ شرایطی از ستاره (مانند **متن** یا *متن* یا ***) برای بولد یا ایتالیک کردن استفاده نکن؛ چون در تلگرام ستاره‌ها بدون استایل و زشت چاپ می‌شوند!
- برای بولد و برجسته کردن تیترها، عناوین و کلمات مهم، فقط و فقط از تگ HTML تلگرام <b>عنوان</b> استفاده کن.
- برای کدهای تک‌خطی یا عبارات مهم انگلیسی از <code>کد</code> استفاده کن.
- برای بولت‌پوینت‌ها و لیست‌ها، اصلاً از * یا - استفاده نکن؛ به جای آن همیشه از ایموجی‌های تمیز مانند 🔹 یا ▫️ یا شماره‌های فارسی (۱. ۲.) استفاده کن.
"""

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
            "name": "add_assignment",
            "description": "افزودن یک تکلیف جدید به سیستم (فقط مخصوص ادمین و مالک مدرسه)",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "عنوان تکلیف (مثلاً: تمرین‌های فصل ۳ هندسه)",
                    },
                    "description": {
                        "type": "string",
                        "description": "توضیحات کامل تکلیف",
                    },
                    "due_date": {
                        "type": "string",
                        "description": "تاریخ موعد تحویل به فرمت YYYY-MM-DD",
                    },
                    "subject": {
                        "type": "string",
                        "description": "نام درس (مثلاً ریاضی، فیزیک، زیست)",
                    },
                },
                "required": ["title", "due_date"],
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

            new_assignment = models.Assignment(
                title=title,
                description=description,
                due_date=due_dt,
                subject_id=subject,
                category=subject,
                owner_id=current_user.id,
                creator_id=current_user.id,
            )
            db.add(new_assignment)
            db.commit()
            db.refresh(new_assignment)

            return {
                "success": True,
                "message": f"تکلیف '{title}' با موفقیت توسط {current_user.username} در سامانه ثبت شد!",
                "assignment_id": new_assignment.id,
            }

        return {"success": False, "error": f"ابزار ناشناخته: {name}"}
    except Exception as exc:
        logger.error("Error executing tool %s: %s", name, exc)
        return {"success": False, "error": str(exc)}


async def ask_universal_ai_agent(
    user_prompt: str,
    api_key: str,
    db: Session,
    base_url: str = "https://openrouter.ai/api/v1",
    model_name: str = "openai/gpt-4o-mini",
    current_user: Optional[models.User] = None,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Universal OpenAI-compatible chat completions caller with Tools / Function Calling.

    Works natively with OpenRouter, Grok (xAI), DeepSeek, OpenAI, Groq, Together, and self-hosted models.
    """
    if not api_key:
        return "⚠️ کلید API هوش مصنوعی هنوز در پنل مدیریت مدرسه تنظیم نشده است."

    clean_base = (base_url or "https://openrouter.ai/api/v1").rstrip("/")
    if not clean_base.endswith("/chat/completions"):
        endpoint_url = f"{clean_base}/chat/completions"
    else:
        endpoint_url = clean_base

    clean_model = model_name.strip() if model_name else "openai/gpt-4o-mini"

    status = school_knowledge.get_current_school_status()
    user_info = (
        f"کاربر صحبت‌کننده: {current_user.username} (نقش: {current_user.role})"
        if current_user
        else "کاربر صحبت‌کننده: هنوز اکانت تلگرام خود را به حساب کاربری ArchSchool لینک نکرده است."
    )
    time_context = (
        f"اطلاعات زنده زمانی و تقویم مدرسه:\n"
        f"- امروز: {status['today_fa']} | ساعت محلی رسمی ایران: {status['current_time']}\n"
        f"- وضعیت لحظه‌ای مدرسه: {status['bell_status']}\n"
        f"- فردا: {status['tomorrow_fa']}\n"
        f"- روز مدرسه بعدی: {status['next_school_day']}"
    )

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_INSTRUCTION},
    ]

    if conversation_history:
        messages.extend(conversation_history)

    messages.append({
        "role": "user",
        "content": f"[{time_context}]\n[{user_info}]\n{user_prompt}",
    })

    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://archschool.vidxsepehr.ir",
        "X-Title": "ArchSchool Assistant",
    }

    payload: Dict[str, Any] = {
        "model": clean_model,
        "messages": messages,
        "tools": OPENAI_TOOLS,
        "tool_choice": "auto",
        "temperature": 0.7,
        "max_tokens": 800,
    }

    try:
        async with httpx.AsyncClient(timeout=35.0) as client:
            resp = await client.post(endpoint_url, json=payload, headers=headers)
            if resp.status_code != 200:
                logger.error("AI provider error %s from %s: %s", resp.status_code, endpoint_url, resp.text)
                return f"⚠️ خطای ارائه‌دهنده هوش مصنوعی ({resp.status_code}): {resp.text[:150]}"

            data = resp.json()
            choices = data.get("choices", [])
            if not choices:
                return "پاسخی از هوش مصنوعی دریافت نشد."

            first_choice = choices[0]
            choice_message = first_choice.get("message", {})
            tool_calls = choice_message.get("tool_calls")

            # --- Tool Calling Branch ---
            if tool_calls:
                # Add assistant message with tool_calls to history
                messages.append(choice_message)

                for tc in tool_calls:
                    call_id = tc.get("id") or "call_1"
                    fn_data = tc.get("function", {})
                    fn_name = fn_data.get("name", "")
                    fn_args_raw = fn_data.get("arguments", "{}")
                    try:
                        fn_args = json.loads(fn_args_raw) if isinstance(fn_args_raw, str) else fn_args_raw
                    except Exception:
                        fn_args = {}

                    logger.info("Universal AI invoking tool: %s with args: %s", fn_name, fn_args)
                    tool_output = execute_tool(fn_name, fn_args, db, current_user)

                    # Append tool result message
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": json.dumps(tool_output, ensure_ascii=False),
                    })

                # Follow-up request to get final friendly response
                followup_payload = {
                    "model": clean_model,
                    "messages": messages,
                    "tools": OPENAI_TOOLS,
                    "temperature": 0.7,
                    "max_tokens": 800,
                }
                followup_resp = await client.post(endpoint_url, json=followup_payload, headers=headers)
                if followup_resp.status_code == 200:
                    followup_data = followup_resp.json()
                    followup_choices = followup_data.get("choices", [])
                    if followup_choices:
                        final_content = followup_choices[0].get("message", {}).get("content", "")
                        return final_content or "انجام شد!"

            # Normal text content
            content = choice_message.get("content", "")
            return content or "متوجه پیامت نشدم، لطفاً دوباره بگو!"

    except httpx.TimeoutException:
        logger.error("AI provider timeout to %s", endpoint_url)
        return "⚠️ پاسخ ارائه‌دهنده هوش مصنوعی بیش از حد طول کشید. لطفاً مجدداً تلاش کنید."
    except Exception as exc:
        logger.error("Universal AI agent exception: %s", exc)
        return f"⚠️ در ارتباط با هوش مصنوعی مشکلی رخ داد: {str(exc)[:100]}"
