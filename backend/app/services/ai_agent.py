import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..analytics import build_leaderboard

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
"""

OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_my_status",
            "description": "دریافت آمار شخصی، استریک، رتبه در لیدربورد و تکالیف باقی‌مانده کاربر صحبت‌کننده",
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
            "description": "دریافت لیست تکالیف جاری و فعال کلاس به همراه موعد تحویل (ددلاین)",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "تعداد تکالیف (پیش‌فرض ۵)",
                    }
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
            "description": "دریافت برنامه زمانی کلاس‌ها و زنگ‌های مدرسه",
            "parameters": {
                "type": "object",
                "properties": {},
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

    user_info = (
        f"کاربر صحبت‌کننده: {current_user.username} (نقش: {current_user.role})"
        if current_user
        else "کاربر صحبت‌کننده: هنوز اکانت تلگرام خود را به حساب کاربری ArchSchool لینک نکرده است."
    )

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_INSTRUCTION},
    ]

    if conversation_history:
        messages.extend(conversation_history)

    messages.append({
        "role": "user",
        "content": f"[{user_info}]\n{user_prompt}",
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
