import logging
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from ..database import get_db
from ..dependencies import get_current_admin, get_current_user
from ..services import ai_agent, telegram_bot

logger = logging.getLogger("archschool.telegram_router")

router = APIRouter(prefix="/telegram", tags=["telegram"])


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


@router.post("/webhook", include_in_schema=False)
async def telegram_webhook(request: Request, db: Session = Depends(get_db)):
    """Receives incoming updates from Telegram Webhook."""
    try:
        update: Dict[str, Any] = await request.json()
    except Exception:
        return Response(status_code=400)

    token = telegram_bot.get_bot_setting(db, "telegram_bot_token")
    ai_key = telegram_bot.get_bot_setting(db, "ai_api_key") or telegram_bot.get_bot_setting(db, "gemini_api_key")
    base_url = telegram_bot.get_bot_setting(db, "ai_base_url", "https://openrouter.ai/api/v1")
    model_name = telegram_bot.get_bot_setting(db, "ai_model", "openai/gpt-4o-mini")
    enabled = telegram_bot.get_bot_setting(db, "telegram_bot_enabled", "true").lower() in ("true", "1")

    if not token or not enabled:
        return {"ok": True}

    message = update.get("message") or update.get("edited_message")
    if not message:
        return {"ok": True}

    chat = message.get("chat", {})
    chat_id = chat.get("id")
    chat_type = chat.get("type", "private")
    from_user = message.get("from", {})
    from_id = from_user.get("id")
    from_username = from_user.get("username")
    text = (message.get("text") or "").strip()
    msg_id = message.get("message_id")

    if not text or not chat_id or not from_id:
        return {"ok": True}

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
            return {"ok": True}

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
            return {"ok": True}

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
            return {"ok": True}

        # Clean mention tag from text prompt
        if bot_user:
            text = text.replace(f"@{bot_user}", "").strip()

    # --- 3. Process prompt with Universal AI Agent (OpenRouter, Grok, OpenAI, DeepSeek, etc.) ---
    if not ai_key:
        await telegram_bot.send_telegram_message(
            token, chat_id, "⚠️ کلید هوش مصنوعی در سرور مدرسه هنوز تنظیم نشده است.", reply_to_message_id=msg_id
        )
        return {"ok": True}

    # Fetch recent conversation memory for this chat
    history = telegram_bot.get_chat_history(db, chat_id, limit=10)
    is_recent = telegram_bot.is_recent_conversation(db, chat_id, max_idle_minutes=120)

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

    await telegram_bot.send_telegram_message(
        token, chat_id, ai_reply, parse_mode="HTML", reply_to_message_id=msg_id
    )
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
    base_url = telegram_bot.get_bot_setting(db, "ai_base_url", "https://openrouter.ai/api/v1")
    model_name = telegram_bot.get_bot_setting(db, "ai_model", "openai/gpt-4o-mini")

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
        ai_status = "متصل و فعال" if not test_ai.startswith("⚠️") else f"خطا: {test_ai}"

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
