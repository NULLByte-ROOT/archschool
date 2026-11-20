import asyncio
from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Dict, Optional, Set
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from ..database import SessionLocal, get_db
from ..dependencies import get_current_admin, get_current_user
from ..services import ai_agent, telegram_bot

logger = logging.getLogger("archschool.telegram_router")

router = APIRouter(prefix="/telegram", tags=["telegram"])

_PROCESSED_UPDATE_IDS: Set[int] = set()
_IN_FLIGHT_UPDATE_IDS: Set[int] = set()
_MAX_PROCESSED_CACHE: int = 10000


def _is_duplicate_update(update_id: Optional[int]) -> bool:
    if not update_id:
        return False
    if update_id in _IN_FLIGHT_UPDATE_IDS or update_id in _PROCESSED_UPDATE_IDS:
        return True
    _IN_FLIGHT_UPDATE_IDS.add(update_id)
    return False


def _mark_update_completed(update_id: Optional[int]) -> None:
    if not update_id:
        return
    _IN_FLIGHT_UPDATE_IDS.discard(update_id)
    _PROCESSED_UPDATE_IDS.add(update_id)
    if len(_PROCESSED_UPDATE_IDS) > _MAX_PROCESSED_CACHE:
        try:
            _PROCESSED_UPDATE_IDS.pop()
        except KeyError:
            pass


class BotSettingsUpdate(BaseModel):
    bot_token: Optional[str] = None
    group_id: Optional[str] = None
    ai_provider: Optional[str] = None
    ai_api_key: Optional[str] = None
    ai_base_url: Optional[str] = None
    ai_model: Optional[str] = None
    gemini_api_key: Optional[str] = None
    bot_enabled: Optional[bool] = None


class BotTestRequest(BaseModel):
    message: Optional[str] = None


class FetchModelsRequest(BaseModel):
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    provider: Optional[str] = None


async def _handle_telegram_update_logic(update: Dict[str, Any], db: Session) -> None:
    """Core update processor invoked in the background after 200 OK has been returned."""
    token = telegram_bot.get_bot_setting(db, "telegram_bot_token")
    ai_key = telegram_bot.get_bot_setting(db, "ai_api_key") or telegram_bot.get_bot_setting(db, "gemini_api_key")
    provider = telegram_bot.get_bot_setting(db, "ai_provider", "openrouter")
    def_base, def_model = telegram_bot.get_provider_defaults(provider)
    base_url = telegram_bot.get_bot_setting(db, "ai_base_url") or def_base
    model_name = telegram_bot.get_bot_setting(db, "ai_model") or def_model
    enabled = telegram_bot.get_bot_setting(db, "telegram_bot_enabled", "true").lower() in ("true", "1")

    if not token or not enabled:
        return

    # --- 0. Handle Inline Button Callback Queries (Wizard & Task Toggles) ---
    callback_query = update.get("callback_query")
    if callback_query:
        cb_id = callback_query.get("id")
        cb_data = callback_query.get("data", "")
        cb_from = callback_query.get("from", {})
        cb_from_id = cb_from.get("id")
        cb_msg = callback_query.get("message", {})
        cb_chat = cb_msg.get("chat", {})
        cb_chat_id = cb_chat.get("id")
        cb_msg_id = cb_msg.get("message_id")

        cb_user = db.query(models.User).filter(models.User.telegram_id == cb_from_id).first() if cb_from_id else None

        from app.services import telegram_task_wizard
        if cb_data.startswith("wiz:"):
            await telegram_task_wizard.handle_wizard_callback(
                db, cb_user, cb_data, cb_chat_id, cb_msg_id, cb_id, token
            )
            return

        if cb_data.startswith("task_toggle:"):
            await telegram_task_wizard.handle_toggle_callback(
                db, cb_user, cb_data, cb_chat_id, cb_msg_id, cb_id, token
            )
            return

        await telegram_bot.answer_callback_query(token, cb_id)
        return

    # Only process standard messages; ignore edited_message to prevent duplicate replies
    message = update.get("message")
    if not message:
        return

    chat = message.get("chat", {})
    chat_id = chat.get("id")
    chat_type = chat.get("type", "private")
    from_user = message.get("from", {})
    from_id = from_user.get("id")
    from_username = from_user.get("username")
    text = (message.get("text") or "").strip()
    msg_id = message.get("message_id")

    if not text or not chat_id or not from_id:
        return

    # Find if sender is an authenticated ArchSchool user
    user = db.query(models.User).filter(models.User.telegram_id == from_id).first()

    # --- 1. Handle Private Chat Linking & Commands ---
    if chat_type == "private":
        # Handle link token
        if text.startswith("arch_"):
            linked_user = telegram_bot.link_telegram_user(
                db, telegram_id=from_id, telegram_username=from_username, token=text
            )
            if linked_user:
                reply = (
                    f"🎉 <b>ایول! حسابت با موفقیت وصل شد!</b>\n\n"
                    f"سلام <b>{linked_user.username}</b> عزیز! 🦁👋\n"
                    f"از الان من کاملاً می‌شناسمت و می‌دونم تو سامانه چه کارهایی داری.\n"
                    f"نقش کاربری شما: <b>{'مدیر مدرسه' if linked_user.is_admin else 'دانش‌آموز'}</b>\n\n"
                    f"هر سوالی در مورد تکالیف، استریکت، یا رتبه‌بندی کلاس داشتی همینجا یا تو گروه ازم بپرس! 🔥⚡"
                )
            else:
                reply = (
                    "❌ <b>کد اتصال نامعتبر یا منقضی شده است!</b>\n\n"
                    "لطفاً وارد اپلیکیشن ArchSchool شده، به تب پروفایل بروید و روی دکمه 'دریافت کد اتصال به ربات' بزنید."
                )
            await telegram_bot.send_telegram_message(token, chat_id, reply)
            return

        if text == "/start":
            if user:
                reply = (
                    f"سلام <b>{user.username}</b> عزیز! 🚀\n"
                    f"حساب شما متصل است. هر سوالی درباره درس‌ها، تکالیف و استریکت داری بپرس!"
                )
            else:
                reply = (
                    "سلام همکلاسی! 👋 به ربات هوشمند <b>ArchSchool</b> خوش اومدی! 🎒✨\n\n"
                    "برای اینکه بتونم کمکت کنم و وضعیت تکالیف و استریکت رو بگم:\n"
                    "۱. اپلیکیشن ArchSchool رو باز کن.\n"
                    "۲. برو تو تب پروفایل و کد اتصال تلگرام رو کپی کن.\n"
                    "۳. کد رو همینجا برام بفرست تا حسابت فعال بشه! 🔥"
                )
            await telegram_bot.send_telegram_message(token, chat_id, reply)
            return

    # --- 2. Handle Group Chat Mention / Reply Check ---
    elif chat_type in ("group", "supergroup"):
        # Check if the bot was mentioned or replied to
        is_reply_to_bot = (
            message.get("reply_to_message", {}).get("from", {}).get("is_bot") is True
        )
        entities = message.get("entities", [])
        bot_mentioned = any(e.get("type") == "mention" for e in entities)

        # Get bot's own username to verify mention if available
        bot_user = telegram_bot.get_bot_setting(db, "telegram_bot_username", "")
        if bot_user and f"@{bot_user.lower()}" in text.lower():
            bot_mentioned = True

        # If not directed to bot, ignore group chatter
        if not bot_mentioned and not is_reply_to_bot and not text.startswith("/"):
            return

        # Clean mention tag from text prompt
        if bot_user:
            text = text.replace(f"@{bot_user}", "").strip()

    # --- 3. Interactive Button-Based Assignment Creation Interceptor ---
    is_add_cmd = any(k in text for k in (
        "تکلیف اد کن", "تکلیف اد", "اد کن", "اد کردن تکلیف", "تکلیف اد کنید",
        "تکلیف اضافه کن", "تکلیف اضافه", "افزودن تکلیف", "ثبت تکلیف", "تکلیف جدید",
        "تکلیف بزار", "تکلیف بذار", "مشق اضافه کن", "مشق اد کن", "مشق بزار", "مشق بذار",
        "/new_assignment", "/add_assignment", "میخوام تکلیف بسازم", "میخوام تکلیف اضافه کنم"
    ))
    if is_add_cmd:
        if not user:
            await telegram_bot.send_telegram_message(
                token, chat_id,
                "داش تو اصلاً کی هستی که دستور اد کردن تکلیف میدی؟! 😏\nتو سیستم مدرسه نشناختمت سلطان! اول کد اتصالت رو از تب پروفایل اپلیکیشن برام بفرست تا بشناسمت.",
                reply_to_message_id=msg_id
            )
            return
        if not (user.is_admin or user.role in ("admin", "owner")):
            await telegram_bot.send_telegram_message(
                token, chat_id,
                f"داش {user.username}، تو که مدیر یا صاحب مدرسه نیستی بخوای تکلیف اد کنی! برو مشقاتو بنویس تکلیفت نسوزه 😂🔥",
                reply_to_message_id=msg_id
            )
            return

        from app.services import telegram_task_wizard
        await telegram_task_wizard.start_add_task_wizard(token, chat_id, user, reply_to_message_id=msg_id)
        return

    # --- 4. Direct Task Completion Interceptor (100% immune to LLM hallucination) ---
    is_toggle_cmd = any(k in text for k in (
        "تیک بزن", "تیک زدن", "تیک بردار", "تیکش رو بردار", "تیکش بردار",
        "تیکمو بزن", "تیکش کن", "تیک بزنم", "انجام شد", "انجام دادم", "حل کردم", "تیک بخوره"
    ))
    if is_toggle_cmd:
        action = "uncomplete" if any(w in text for w in ("بردار", "حذف", "برداشتن", "نکردم")) else "complete"
        scope = "all" if any(w in text for w in ("همه", "تمام", "همشون", "همه‌شون")) else (
            "day" if any(d in text for d in ("شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "امروز", "فردا")) else "single"
        )
        target_day = ""
        if scope == "day":
            for d in ("شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "امروز", "فردا"):
                if d in text:
                    target_day = d
                    break

        res = ai_agent.execute_tool(
            "toggle_assignment_completion",
            {"action": action, "scope": scope, "assignment_query": text, "target_day": target_day},
            db,
            user,
        )

        if res.get("success"):
            titles = "، ".join(res.get("modified_titles", []))
            pct = res.get("new_completion_percentage", 0)
            streak = res.get("current_streak", 0)
            act_text = "انجام شد و تیک خورد" if action == "complete" else "تیک آن برداشته شد"
            reply_text = (
                f"🎉 <b>تکلیف {titles} با موفقیت {act_text}!</b> 🔥⚡\n\n"
                f"📊 درصد کل تکالیف انجام‌شده شما: <b>{pct}٪</b>\n"
                f"🔥 استریک جاری شما: <b>{streak} روز</b>\n\n"
                f"<i>برای جزئیات بیشتر و مشاهده نمودارها به اپلیکیشن ArchSchool مراجعه کنید.</i>"
            )
        else:
            err = res.get("error") or res.get("message") or "تکلیفی برای تیک زدن پیدا نشد."
            reply_text = f"⚠️ {err}"

        await telegram_bot.send_telegram_message(token, chat_id, reply_text, reply_to_message_id=msg_id)
        return

    # --- 5. Process general prompt with Universal AI Agent ---
    if not ai_key:
        await telegram_bot.send_telegram_message(
            token, chat_id, "⚠️ کلید هوش مصنوعی در سرور مدرسه هنوز تنظیم نشده است.", reply_to_message_id=msg_id
        )
        return

    # Fetch compact recent conversation memory (6 messages) for fast TTFT
    history = telegram_bot.get_chat_history(db, chat_id, limit=6)
    is_recent = telegram_bot.is_recent_conversation(db, chat_id, max_idle_minutes=120)

    # Instant visual feedback: send 'typing' action immediately to Telegram header
    asyncio.create_task(telegram_bot.send_chat_action(token, chat_id, "typing"))

    ai_reply = await ai_agent.ask_universal_ai_agent(
        user_prompt=text,
        api_key=ai_key,
        db=db,
        base_url=base_url,
        model_name=model_name,
        current_user=user,
        conversation_history=history,
        is_recent=is_recent,
    )

    # Persist user prompt and assistant response to chat history for multi-turn sessions
    telegram_bot.save_chat_history(db, chat_id, role="user", content=text, user_id=user.id if user else None)
    telegram_bot.save_chat_history(db, chat_id, role="assistant", content=ai_reply, user_id=user.id if user else None)

    # Attach interactive action button ONLY when user asks to add/create a task (no buttons for ticking)
    reply_markup = None
    add_task_keywords = (
        "افزودن تکلیف", "اضافه کردن تکلیف", "ثبت تکلیف", "تکلیف جدید",
        "تکلیف بزار", "تکلیف بذار", "تکلیف اضافه", "تکلیف ثبت", "ایجاد تکلیف",
        "مشق اضافه", "مشق ثبت", "تکلیف بده", "تکلیف اد کن", "تکلیف اد", "اد کن", "اد کردن"
    )
    if user and (user.is_admin or user.role in ("admin", "owner")):
        if any(k in text for k in add_task_keywords):
            reply_markup = {
                "inline_keyboard": [
                    [{"text": "➕ افزودن تکلیف جدید با دکمه", "callback_data": "wiz:s1"}]
                ]
            }

    await telegram_bot.send_telegram_message(
        token, chat_id, ai_reply, parse_mode="HTML", reply_to_message_id=msg_id, reply_markup=reply_markup
    )


async def _process_telegram_update_task(update: Dict[str, Any], update_id: Optional[int]) -> None:
    try:
        with SessionLocal() as db:
            await _handle_telegram_update_logic(update, db)
    except Exception as exc:
        logger.error("Error processing telegram update %s: %s", update_id, exc, exc_info=True)
    finally:
        _mark_update_completed(update_id)


@router.post("/webhook", include_in_schema=False)
async def telegram_webhook(request: Request, background_tasks: BackgroundTasks):
    """Receives incoming updates from Telegram Webhook and acknowledges immediately (zero timeout/retry)."""
    try:
        update: Dict[str, Any] = await request.json()
    except Exception:
        return Response(status_code=400)

    update_id = update.get("update_id")
    if _is_duplicate_update(update_id):
        logger.info("Ignoring duplicate or in-flight update_id: %s", update_id)
        return {"ok": True}

    background_tasks.add_task(_process_telegram_update_task, update, update_id)
    return {"ok": True}


# --------------------------------------------------------------------------
# Admin & Settings Endpoints
# --------------------------------------------------------------------------

@router.get("/settings")
def get_settings(
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """Retrieve Telegram bot and AI configuration (Admin/Owner only)."""
    return telegram_bot.get_all_bot_settings(db)


@router.put("/settings")
async def update_settings(
    payload: BotSettingsUpdate,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """Update Telegram bot and AI configuration (Admin/Owner only)."""
    if payload.bot_token is not None:
        token = payload.bot_token.strip()
        telegram_bot.set_bot_setting(db, "telegram_bot_token", token)
        if token:
            # Detect bot identity
            info = await telegram_bot.get_bot_identity(token)
            if info and "username" in info:
                telegram_bot.set_bot_setting(db, "telegram_bot_username", info["username"])

            # Setup webhook automatically
            host_url = getattr(settings, "HOST_URL", "https://archschool.vidxsepehr.ir").rstrip("/")
            webhook_url = f"{host_url}/api/v1/telegram/webhook"
            res = await telegram_bot.setup_telegram_webhook(token, webhook_url)
            logger.info("Auto-registered Telegram webhook: %s -> %s", webhook_url, res)

    if payload.group_id is not None:
        telegram_bot.set_bot_setting(db, "telegram_group_id", payload.group_id.strip())

    if payload.ai_provider is not None:
        telegram_bot.set_bot_setting(db, "ai_provider", payload.ai_provider.strip())

    if payload.ai_api_key is not None:
        telegram_bot.set_bot_setting(db, "ai_api_key", payload.ai_api_key.strip())
    elif payload.gemini_api_key is not None:
        telegram_bot.set_bot_setting(db, "ai_api_key", payload.gemini_api_key.strip())

    if payload.ai_base_url is not None:
        telegram_bot.set_bot_setting(db, "ai_base_url", payload.ai_base_url.strip())

    if payload.ai_model is not None:
        telegram_bot.set_bot_setting(db, "ai_model", payload.ai_model.strip())

    if payload.bot_enabled is not None:
        telegram_bot.set_bot_setting(
            db, "telegram_bot_enabled", "true" if payload.bot_enabled else "false"
        )

    return {"ok": True, "settings": telegram_bot.get_all_bot_settings(db)}


@router.post("/test")
async def test_telegram(
    payload: BotTestRequest,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """Send a test message to the configured group and verify bot & AI API."""
    token = telegram_bot.get_bot_setting(db, "telegram_bot_token")
    group_id = telegram_bot.get_bot_setting(db, "telegram_group_id")
    ai_key = telegram_bot.get_bot_setting(db, "ai_api_key") or telegram_bot.get_bot_setting(db, "gemini_api_key")
    provider = telegram_bot.get_bot_setting(db, "ai_provider", "openrouter")
    def_base, def_model = telegram_bot.get_provider_defaults(provider)
    base_url = telegram_bot.get_bot_setting(db, "ai_base_url") or def_base
    model_name = telegram_bot.get_bot_setting(db, "ai_model") or def_model

    if not token:
        raise HTTPException(status_code=400, detail="توکن ربات تلگرام تنظیم نشده است.")

    # 1. Test Bot Token
    identity = await telegram_bot.get_bot_identity(token)
    if not identity:
        raise HTTPException(status_code=400, detail="توکن تلگرام نامعتبر است یا ارتباط برقرار نشد.")

    # 2. Test AI API Key if present
    ai_status = "تنظیم نشده"
    if ai_key:
        test_ai = await ai_agent.ask_universal_ai_agent(
            user_prompt="یک پیام کوتاه تستی و سلام بگو",
            api_key=ai_key,
            db=db,
            base_url=base_url,
            model_name=model_name,
            current_user=admin,
        )
        test_ai_str = str(test_ai or "")
        ai_status = "متصل و فعال" if not test_ai_str.startswith("⚠️") else f"خطا: {test_ai_str}"

    # 3. Test sending message to group if group_id is present
    group_sent = False
    if group_id:
        test_msg = payload.message or (
            f"🤖 <b>تست اتصال ربات تلگرام ArchSchool</b> ✨\n\n"
            f"ربات <b>@{identity.get('username')}</b> با موفقیت به سرور متصل شد!\n"
            f"ارائه‌دهنده هوش مصنوعی: <code>{model_name}</code> ({ai_status})\n"
            f"ارسال شده توسط ادمین: <b>{admin.username}</b>"
        )
        group_sent = await telegram_bot.send_telegram_message(token, group_id, test_msg)

    return {
        "ok": True,
        "bot_username": identity.get("username"),
        "bot_first_name": identity.get("first_name"),
        "ai_status": ai_status,
        "group_message_sent": group_sent,
    }


@router.post("/models")
async def get_available_models(
    payload: FetchModelsRequest,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """Dynamically query available chat models from the given provider's /models endpoint."""
    key = (
        payload.api_key
        or telegram_bot.get_bot_setting(db, "ai_api_key")
        or telegram_bot.get_bot_setting(db, "gemini_api_key")
    )
    provider = payload.provider or telegram_bot.get_bot_setting(db, "ai_provider", "openrouter")
    def_base, _ = telegram_bot.get_provider_defaults(provider)
    base_url = payload.base_url or telegram_bot.get_bot_setting(db, "ai_base_url") or def_base

    if not key or not key.strip():
        return {"ok": False, "models": [], "error": "کلید API وارد نشده است."}

    models_list = await telegram_bot.fetch_provider_models(key.strip(), base_url.strip())
    return {"ok": True, "models": models_list}


# --------------------------------------------------------------------------
# User Link Token Endpoints
# --------------------------------------------------------------------------

@router.get("/token")
def get_user_token(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Get the current user's link token or generate one if not present."""
    token = current_user.telegram_link_token
    if not token and not current_user.telegram_id:
        token = telegram_bot.generate_user_link_token(db, current_user)

    return {
        "token": token,
        "is_linked": bool(current_user.telegram_id),
        "telegram_username": current_user.telegram_username,
        "telegram_id": current_user.telegram_id,
    }


@router.post("/token/revoke")
def revoke_user_token(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Unlink current telegram connection and generate a new secret link token."""
    telegram_bot.unlink_telegram_user(db, current_user)
    new_token = telegram_bot.generate_user_link_token(db, current_user)
    return {
        "token": new_token,
        "is_linked": False,
        "telegram_username": None,
    }
