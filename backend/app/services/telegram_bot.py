import asyncio
import logging
import secrets
from typing import Any, Dict, List, Optional
import httpx
from sqlalchemy.orm import Session

from .. import models
from ..analytics import build_leaderboard

logger = logging.getLogger("archschool.telegram")

TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}"


def get_bot_setting(db: Session, key: str, default: str = "") -> str:
    """Read a setting from bot_settings table."""
    setting = db.query(models.BotSetting).filter(models.BotSetting.key == key).first()
    return setting.value if setting else default


def set_bot_setting(db: Session, key: str, value: str) -> None:
    """Insert or update a setting in bot_settings table."""
    setting = db.query(models.BotSetting).filter(models.BotSetting.key == key).first()
    if setting:
        setting.value = value
    else:
        setting = models.BotSetting(key=key, value=value)
        db.add(setting)
    db.commit()


def get_all_bot_settings(db: Session) -> Dict[str, Any]:
    """Retrieve all bot-related settings as a dictionary."""
    rows = db.query(models.BotSetting).all()
    data = {r.key: r.value for r in rows}
    api_key = data.get("ai_api_key") or data.get("gemini_api_key", "")
    return {
        "bot_token": data.get("telegram_bot_token", ""),
        "group_id": data.get("telegram_group_id", ""),
        "ai_provider": data.get("ai_provider", "openrouter"),
        "ai_api_key": api_key,
        "ai_base_url": data.get("ai_base_url", "https://openrouter.ai/api/v1"),
        "ai_model": data.get("ai_model", "openai/gpt-4o-mini"),
        "bot_enabled": data.get("telegram_bot_enabled", "true").lower() in ("true", "1", "yes"),
        "has_token": bool(data.get("telegram_bot_token")),
        "has_ai": bool(api_key),
    }


def generate_user_link_token(db: Session, user: models.User) -> str:
    """Generate a fresh unique link token for a user to send to the Telegram bot."""
    token = f"arch_{secrets.token_hex(12)}"
    user.telegram_link_token = token
    db.commit()
    return token


def unlink_telegram_user(db: Session, user: models.User) -> None:
    """Remove Telegram connection from user account."""
    user.telegram_id = None
    user.telegram_username = None
    user.telegram_link_token = None
    db.commit()


def link_telegram_user(
    db: Session, telegram_id: int, telegram_username: Optional[str], token: str
) -> Optional[models.User]:
    """Link a Telegram account to an ArchSchool user using their link token."""
    clean_token = token.strip()
    user = (
        db.query(models.User)
        .filter(models.User.telegram_link_token == clean_token)
        .first()
    )
    if not user:
        return None

    # Check if another user previously had this telegram_id and unlink them
    prev_user = (
        db.query(models.User)
        .filter(models.User.telegram_id == telegram_id, models.User.id != user.id)
        .first()
    )
    if prev_user:
        prev_user.telegram_id = None
        prev_user.telegram_username = None

    user.telegram_id = telegram_id
    user.telegram_username = telegram_username
    # Revoke used token for security
    user.telegram_link_token = None
    db.commit()
    return user


async def send_telegram_message(
    token: str,
    chat_id: str | int,
    text: str,
    parse_mode: str = "HTML",
    reply_to_message_id: Optional[int] = None,
) -> bool:
    """Send a message via Telegram Bot HTTP API."""
    if not token or not chat_id:
        return False

    url = f"{TELEGRAM_API_BASE.format(token=token)}/sendMessage"
    payload: Dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
    }
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                return True
            logger.warning("Telegram sendMessage error: %s %s", resp.status_code, resp.text)
    except Exception as exc:
        logger.error("Failed to send Telegram message: %s", exc)
    return False


async def setup_telegram_webhook(token: str, webhook_url: str, secret_token: Optional[str] = None) -> Dict[str, Any]:
    """Register the webhook URL with Telegram API."""
    if not token:
        return {"ok": False, "error": "Token is required"}

    url = f"{TELEGRAM_API_BASE.format(token=token)}/setWebhook"
    payload: Dict[str, Any] = {
        "url": webhook_url,
        "allowed_updates": ["message", "edited_message", "callback_query"],
        "drop_pending_updates": True,
    }
    if secret_token:
        payload["secret_token"] = secret_token

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload)
            return resp.json()
    except Exception as exc:
        logger.error("Failed to setup Telegram webhook: %s", exc)
        return {"ok": False, "error": str(exc)}


async def get_bot_identity(token: str) -> Optional[Dict[str, Any]]:
    """Fetch the bot's username and name."""
    if not token:
        return None
    url = f"{TELEGRAM_API_BASE.format(token=token)}/getMe"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("result")
    except Exception as exc:
        logger.error("Failed to get bot identity: %s", exc)
    return None


async def check_and_broadcast_top1(db: Session) -> Optional[str]:
    """Check if the #1 rank in the leaderboard has changed, and broadcast to group if so."""
    token = get_bot_setting(db, "telegram_bot_token")
    group_id = get_bot_setting(db, "telegram_group_id")
    enabled = get_bot_setting(db, "telegram_bot_enabled", "true").lower() in ("true", "1")

    if not token or not group_id or not enabled:
        return None

    try:
        entries, _ = build_leaderboard(db)
        if not entries:
            return None

        top_entry = entries[0]
        top_user = top_entry["user"]
        top_user_id = str(top_user.id)
        top_username = top_user.username
        percentage = round(top_entry.get("completion_percentage", 0), 1)
        streak = top_entry.get("current_streak", 0)

        last_top_id = get_bot_setting(db, "last_top1_user_id")
        last_top_name = get_bot_setting(db, "last_top1_username", "هیچ‌کس")

        # If it's the very first time setting up, just record the leader without spamming
        if not last_top_id:
            set_bot_setting(db, "last_top1_user_id", top_user_id)
            set_bot_setting(db, "last_top1_username", top_username)
            return None

        # If the king of the leaderboard has changed!
        if last_top_id != top_user_id:
            set_bot_setting(db, "last_top1_user_id", top_user_id)
            set_bot_setting(db, "last_top1_username", top_username)

            announcement = (
                f"🚨 <b>زلزله در لیدربورد کلاس! تاج و تخت جابه‌جا شد!</b> 👑🔥\n\n"
                f"🏆 <b>{top_username}</b> کولاک کرد و با استریک آتشین <b>{streak} روزه</b> "
                f"و موفقیت <b>{percentage}%</b>، صدر جدول رو از <i>{last_top_name}</i> پس گرفت و سلطان جدید کلاس شد! 🦁💪\n\n"
                f"بچه‌ها کجایید که جا موندید؟! رقابت داره به اوج خودش می‌رسه! 😎⚡\n"
                f"<i>(برای مشاهده رتبه خودتون، داخل اپ بخش رتبه‌بندی رو ببینید)</i>"
            )

            await send_telegram_message(token, group_id, announcement)
            logger.info("Broadcasted top 1 leaderboard change: %s took rank 1", top_username)
            return top_username
    except Exception as exc:
        logger.error("Failed to check and broadcast top 1: %s", exc)
    return None
