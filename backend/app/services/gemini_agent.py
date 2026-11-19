import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..analytics import build_leaderboard

logger = logging.getLogger("archschool.gemini")

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
FALLBACK_MODELS = ["gemini-flash-latest", "gemini-3.8-flash", "gemini-3.5-flash"]

SYSTEM_INSTRUCTION = """
تو دستیار هوشمند، رفیق و همکلاسی پرانرژی بچه‌های مدرسه در سامانه ArchSchool هستی! 🚀
شخصیت و لحن تو:
- فوق‌العاده باانرژی، صمیمی، خودمانی و رفاقتی هستی.
- از ایموجی‌های جذاب (🔥, ⚡, 👑, 😎, 📚, 🦁, 🎯) زیاد و به‌جا استفاده می‌کنی.
- بچه‌ها رو همیشه به رقابت درسی، افزایش استریک و بالا کشیدن خودشون در لیدربورد تشویق و ترغیب می‌کنی.
- در پروژه هیچ نقشی به اسم «معلم» وجود نداره؛ کاربران یا دانش‌آموزن یا مدیر/مالک مدرسه (Admin / Owner).
- اگر کسی ازت جواب آماده برای حل یا تقلب در یک تکلیف خواست، کل جواب رو براش حل نمی‌کنی؛ بلکه با زبان ساده راهنمایی و کمکش می‌کنی تا خودش حل کنه و استریکش نسوزه!
- برای پاسخ به وضعیت تکالیف، رتبه‌بندی، برنامه زنگ‌ها و ... حتماً از ابزارهایی که در اختیارت هست (Function Calling) استفاده کن و اطلاعات دقیق بده.
- همیشه پاسخ‌ها رو به زبان فارسی روان، خودمانی و جذاب بنویس.
"""

TOOL_DEFINITIONS = [
    {
        "name": "get_my_status",
        "description": "دریافت آمار شخصی، استریک، رتبه در لیدربورد و تکالیف باقی‌مانده کاربر صحبت‌کننده",
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        },
    },
    {
        "name": "get_class_assignments",
        "description": "دریافت لیست تکالیف جاری و فعال کلاس به همراه موعد تحویل (ددلاین)",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "limit": {
                    "type": "INTEGER",
                    "description": "تعداد تکالیف (پیش‌فرض ۵)",
                }
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

            # Find uncompleted assignments
            completed_ids = (
                select(models.AssignmentCompletion.assignment_id)
                .filter(models.AssignmentCompletion.user_id == current_user.id)
            )
            pending = (
                db.query(models.Assignment)
                .filter(
                    models.Assignment.deleted_at.is_(None),
                    ~models.Assignment.id.in_(completed_ids),
                )
                .order_by(models.Assignment.due_date.asc())
                .limit(5)
                .all()
            )

            pending_list = [
                {
                    "title": a.title,
                    "subject": a.subject_id or a.category or "عمومی",
                    "due_date": a.due_date.isoformat() if a.due_date else "نامشخص",
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
            }

        elif name == "get_class_assignments":
            limit = args.get("limit", 5)
            assignments = (
                db.query(models.Assignment)
                .filter(models.Assignment.deleted_at.is_(None))
                .order_by(models.Assignment.due_date.asc())
                .limit(limit)
                .all()
            )
            return {
                "success": True,
                "assignments": [
                    {
                        "id": a.id,
                        "title": a.title,
                        "description": a.description,
                        "subject": a.subject_id or a.category or "عمومی",
                        "due_date": a.due_date.isoformat() if a.due_date else "نامشخص",
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


async def ask_gemini_agent(
    user_prompt: str,
    api_key: str,
    db: Session,
    current_user: Optional[models.User] = None,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    model_name: str = "gemini-3.5-flash-lite",
) -> str:
    """Send user prompt to Gemini Flash with function calling support."""
    if not api_key:
        return "⚠️ کلید API هوش مصنوعی جمینای در پنل مدیریت مدرسه هنوز تنظیم نشده است."

    clean_key = api_key.strip()

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

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": clean_key,
        "User-Agent": "Mozilla/5.0",
    }

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

    models_to_try = [model_name] + [m for m in FALLBACK_MODELS if m != model_name]

    try:
        async with httpx.AsyncClient(timeout=25.0, headers=headers) as client:
            resp = None
            used_model = model_name

            for m in models_to_try:
                target_url = GEMINI_API_URL.format(model=m)
                resp = await client.post(target_url, json=payload)
                if resp.status_code == 200:
                    used_model = m
                    break
                logger.warning("Gemini model %s returned %s: %s", m, resp.status_code, resp.text[:120])

            if not resp or resp.status_code != 200:
                code = resp.status_code if resp else "timeout"
                return f"⚠️ متاسفانه در ارتباط با هوش مصنوعی خطایی رخ داد: {code}"

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

                # Append model's exact parts (including thoughtSignature)
                contents.append({
                    "role": "model",
                    "parts": parts,
                })
                # Append tool response with role 'user' (v1beta requirement)
                contents.append({
                    "role": "user",
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
                turn2_url = GEMINI_API_URL.format(model=used_model)
                second_resp = await client.post(turn2_url, json=second_payload)
                if second_resp.status_code == 200:
                    second_data = second_resp.json()
                    second_parts = second_data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                    final_text = "".join(p.get("text", "") for p in second_parts if "text" in p)
                    return final_text or "انجام شد!"

            # Normal text response
            text_response = "".join(p.get("text", "") for p in parts if "text" in p)
            return text_response or "متوجه پیامت نشدم، لطفاً دوباره بگو!"

    except Exception as exc:
        logger.error("Gemini agent exception: %s", exc)
        return "⚠️ در برقراری ارتباط با هوش مصنوعی مشکلی پیش آمد. لطفاً چند لحظه بعد تلاش کنید."
