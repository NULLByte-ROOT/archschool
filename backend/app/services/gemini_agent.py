import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import httpx
from sqlalchemy import select, or_
from sqlalchemy.orm import Session

from .. import models
from ..analytics import build_leaderboard

logger = logging.getLogger("archschool.gemini")

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"

SYSTEM_INSTRUCTION = """
تو دستیار هوشمند، رفیق و همکلاسی پرانرژی بچه‌های مدرسه در اپلیکیشن ArchSchool هستی! 🚀
شخصیت و لحن تو:
- فوق‌العاده باانرژی، صمیمی، خودمانی و رفاقتی هستی.
- از ایموجی‌های جذاب (🔥, ⚡, 👑, 😎, 📚, 🦁, 🎯) زیاد و به‌جا استفاده می‌کنی.
- بچه‌ها رو همیشه به رقابت درسی، افزایش استریک و بالا کشیدن خودشون در لیدربورد تشویق و ترغیب می‌کنی.
- در پروژه هیچ نقشی به اسم «معلم» وجود نداره؛ کاربران یا دانش‌آموزن یا مدیر/مالک مدرسه (Admin / Owner).
- اگر کسی ازت جواب آماده برای حل یا تقلب در یک تکلیف خواست، کل جواب رو براش حل نمی‌کنی؛ بلکه با زبان ساده راهنمایی و کمکش می‌کنی تا خودش حل کنه و استریکش نسوزه!
- برای پاسخ به وضعیت تکالیف، رتبه‌بندی، برنامه زنگ‌ها و ... حتماً از ابزارهایی که در اختیارت هست (Function Calling) استفاده کن و اطلاعات دقیق بده.
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

TOOL_DEFINITIONS = [
    {
        "name": "get_my_status",
        "description": "دریافت آمار شخصی کاربر، استریک، رتبه در لیدربورد و لیست تکالیف فعال و باقی‌مانده‌ای که هنوز انجام نداده است",
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        },
    },
    {
        "name": "get_class_assignments",
        "description": "دریافت لیست تکالیف فعال و جاری کلاس (تکالیفی که مهلت تحویل آن‌ها هنوز نگذشته است)",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "limit": {
                    "type": "INTEGER",
                    "description": "تعداد تکالیف (پیش‌فرض ۵)",
                },
                "include_expired": {
                    "type": "BOOLEAN",
                    "description": "آیا تکالیف قدیمی و منقضی‌شده قبلی هم آورده شوند؟ پیش‌فرض false است.",
                },
            },
        },
    },
    {
        "name": "get_leaderboard",
        "description": "مشاهده جدول رتبه‌بندی برتر کلاس (لیدربورد)، درصد موفقیت و استریک‌های برتر",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "top_n": {
                    "type": "INTEGER",
                    "description": "تعداد نفرات برتر برای نمایش (پیش‌فرض ۵)",
                }
            },
        },
    },
    {
        "name": "get_school_schedule",
        "description": "دریافت برنامه زمانی کلاس‌ها و زنگ‌های مدرسه",
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        },
    },
    {
        "name": "add_assignment",
        "description": "افزودن یک تکلیف جدید به سیستم (فقط مخصوص ادمین و مالک مدرسه)",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "title": {
                    "type": "STRING",
                    "description": "عنوان تکلیف (مثلاً: تمرین‌های فصل ۳ هندسه)",
                },
                "description": {
                    "type": "STRING",
                    "description": "توضیحات کامل تکلیف",
                },
                "due_date": {
                    "type": "STRING",
                    "description": "تاریخ موعد تحویل به فرمت YYYY-MM-DD یا تاریخ میلادی/شمسی مشخص",
                },
                "subject": {
                    "type": "STRING",
                    "description": "نام درس (مثلاً ریاضی، فیزیک، زیست)",
                },
            },
            "required": ["title", "due_date"],
        },
    },
]


def execute_tool(
    name: str, args: Dict[str, Any], db: Session, current_user: Optional[models.User]
) -> Dict[str, Any]:
    """Execute python functions corresponding to Gemini function calls."""
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

            pending_list = [
                {
                    "title": a.title,
                    "subject": a.subject_id or a.category or "عمومی",
                    "due_date": a.due_date.strftime("%Y-%m-%d %H:%M") if a.due_date else "بدون مهلت خاص",
                    "is_active": True,
                }
                for a in pending
            ]

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
            now = datetime.utcnow()

            query = db.query(models.Assignment).filter(models.Assignment.deleted_at.is_(None))

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
                return {
                    "success": True,
                    "assignments": [],
                    "total_count": 0,
                    "message": "در حال حاضر هیچ تکلیف فعالی با مهلت تحویل باز در اپلیکیشن وجود ندارد.",
                }

            return {
                "success": True,
                "total_count": len(assignments),
                "assignments": [
                    {
                        "id": a.id,
                        "title": a.title,
                        "description": a.description,
                        "subject": a.subject_id or a.category or "عمومی",
                        "due_date": a.due_date.strftime("%Y-%m-%d %H:%M") if a.due_date else "بدون مهلت خاص",
                        "is_expired": bool(a.due_date and a.due_date < now),
                    }
                    for a in assignments
                ],
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
            schedules = db.query(models.SchoolSchedule).all()
            return {
                "success": True,
                "schedules": [
                    {
                        "bell_number": s.bell_number,
                        "start_time": s.start_time,
                        "end_time": s.end_time,
                        "label": s.label or f"زنگ {s.bell_number}",
                    }
                    for s in schedules
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
                "message": f"تکلیف '{title}' با موفقیت توسط {current_user.username} در اپلیکیشن ثبت شد!",
                "assignment_id": new_assignment.id,
            }

        return {"success": False, "error": f"ابزار ناشناخته: {name}"}
    except Exception as exc:
        logger.error("Error executing tool %s: %s", name, exc)
        return {"success": False, "error": str(exc)}


async def ask_gemini_agent(
    user_prompt: str,
    api_key: str,
    db: Session,
    current_user: Optional[models.User] = None,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    model_name: str = "gemini-2.0-flash",
) -> str:
    """Send user prompt to Gemini Flash with function calling support."""
    if not api_key:
        return "⚠️ کلید API هوش مصنوعی جمینای در پنل مدیریت مدرسه هنوز تنظیم نشده است."

    user_info = (
        f"کاربر سوال‌کننده: {current_user.username} (نقش: {current_user.role})"
        if current_user
        else "کاربر سوال‌کننده: هنوز اکانت تلگرام خود را به حساب کاربری ArchSchool لینک نکرده است."
    )

    contents: List[Dict[str, Any]] = []
    if conversation_history:
        contents.extend(conversation_history)

    contents.append({
        "role": "user",
        "parts": [{"text": f"[{user_info}]\n{user_prompt}"}],
    })

    url = GEMINI_API_URL.format(model=model_name, key=api_key)

    payload: Dict[str, Any] = {
        "system_instruction": {
            "parts": [{"text": SYSTEM_INSTRUCTION}],
        },
        "contents": contents,
        "tools": [
            {
                "function_declarations": TOOL_DEFINITIONS,
            }
        ],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 800,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                logger.warning("Gemini API error %s: %s, falling back to gemini-1.5-flash", resp.status_code, resp.text)
                # Fallback to gemini-1.5-flash
                fallback_url = GEMINI_API_URL.format(model="gemini-1.5-flash", key=api_key)
                resp = await client.post(fallback_url, json=payload)
                if resp.status_code != 200:
                    return f"⚠️ متاسفانه در ارتباط با هوش مصنوعی خطایی رخ داد: {resp.status_code}"

            res_data = resp.json()
            candidates = res_data.get("candidates", [])
            if not candidates:
                return "پاسخی از هوش مصنوعی دریافت نشد."

            first_candidate = candidates[0]
            parts = first_candidate.get("content", {}).get("parts", [])

            # Check for Function Call
            function_call = None
            for p in parts:
                if "functionCall" in p:
                    function_call = p["functionCall"]
                    break

            if function_call:
                tool_name = function_call.get("name")
                tool_args = function_call.get("args", {})
                logger.info("Gemini invoking tool: %s with args: %s", tool_name, tool_args)

                tool_result = execute_tool(tool_name, tool_args, db, current_user)

                # Append model's function call message
                contents.append({
                    "role": "model",
                    "parts": [{"functionCall": function_call}],
                })
                # Append tool response
                contents.append({
                    "role": "function",
                    "parts": [
                        {
                            "functionResponse": {
                                "name": tool_name,
                                "response": {"output": tool_result},
                            }
                        }
                    ],
                })

                # Call Gemini again to format final friendly message
                second_payload = {
                    "system_instruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
                    "contents": contents,
                    "generationConfig": {"temperature": 0.7, "maxOutputTokens": 800},
                }
                second_resp = await client.post(url, json=second_payload)
                if second_resp.status_code == 200:
                    second_data = second_resp.json()
                    second_parts = second_data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                    final_text = "".join(p.get("text", "") for p in second_parts)
                    return final_text or "انجام شد!"

            # Normal text response
            text_response = "".join(p.get("text", "") for p in parts if "text" in p)
            return text_response or "متوجه پیامت نشدم، لطفاً دوباره بگو!"

    except Exception as exc:
        logger.error("Gemini agent exception: %s", exc)
        return "⚠️ در برقراری ارتباط با هوش مصنوعی مشکلی پیش آمد. لطفاً چند لحظه بعد تلاش کنید."
