import asyncio
from datetime import datetime, timedelta, timezone
import json
import logging
import os
import re
import secrets
import traceback
from typing import Any, Dict, List, Optional, Union
import httpx
from sqlalchemy.orm import Session

from .. import models
from ..analytics import build_leaderboard

logger = logging.getLogger("archschool.telegram")

TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}"

PROVIDER_DEFAULTS = {
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "model": "gemini-3.1-flash-lite",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "model": "openai/gpt-oss-120b",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "model": "openai/gpt-4o-mini",
    },
    "xai": {
        "base_url": "https://api.x.ai/v1",
        "model": "grok-2",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
    },
}


def get_provider_defaults(provider: Optional[str]) -> tuple[str, str]:
    """Return default (base_url, model) for a given provider."""
    p_key = (provider or "openrouter").lower().strip()
    preset = PROVIDER_DEFAULTS.get(p_key, PROVIDER_DEFAULTS["openrouter"])
    return preset["base_url"], preset["model"]


async def fetch_provider_models(api_key: str, base_url: str) -> List[Dict[str, str]]:
    """Query the /models endpoint of an OpenAI-compatible provider and return cleaned models list."""
    if not api_key:
        return []
    clean_base = (base_url or "https://openrouter.ai/api/v1").rstrip("/")
    if clean_base.endswith("/chat/completions"):
        clean_base = clean_base[:-len("/chat/completions")]

    # Target Google Gemini directly via Cloudflare WARP IPv6
    is_gemini = "generativelanguage.googleapis.com" in clean_base or "googleapis.com" in clean_base
    if "archschool.vidxsepehr.ir/gemini" in clean_base:
        clean_base = clean_base.replace(
            "https://archschool.vidxsepehr.ir/gemini",
            "https://generativelanguage.googleapis.com",
        )

    models_url = f"{clean_base}/models"
    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    }
    if "openrouter.ai" in clean_base:
        headers["HTTP-Referer"] = "https://archschool.vidxsepehr.ir"
        headers["X-Title"] = "ArchSchool Assistant"

    try:
        from .ai_agent import get_warp_proxy_url
        proxy = get_warp_proxy_url() if is_gemini else None
        async with httpx.AsyncClient(timeout=10.0, proxy=proxy) as client:
            resp = await client.get(models_url, headers=headers)
            if resp.status_code != 200:
                logger.warning(
                    "Failed to fetch models from %s (HTTP %s): %s",
                    models_url,
                    resp.status_code,
                    resp.text[:100],
                )
                if "googleapis.com" in clean_base:
                    return [
                        {"id": "gemini-3.1-flash-lite", "name": "gemini-3.1-flash-lite (فعال و پرسرعت)"},
                        {"id": "gemini-3-flash-preview", "name": "gemini-3-flash-preview"},
                        {"id": "gemma-4-26b-a4b-it", "name": "gemma-4-26b-a4b-it"},
                        {"id": "gemini-3.8-flash", "name": "gemini-3.8-flash"},
                    ]
                return []
            data = resp.json()
            raw_models = data.get("data", [])
            model_items: List[Dict[str, str]] = []
            excluded_keywords = [
                "whisper", "tts", "embedding", "embed", "moderation",
                "safeguard", "prompt-guard", "rerank", "dall-e", "audio",
                "canopylabs", "orpheus", "live", "image", "preview-tts"
            ]
            for item in raw_models:
                m_id = item.get("id") if isinstance(item, dict) else str(item)
                if not m_id:
                    continue
                clean_id = m_id.replace("models/", "")
                lower_id = clean_id.lower()
                if any(k in lower_id for k in excluded_keywords):
                    continue
                model_items.append({"id": clean_id, "name": clean_id})

            def sort_key(m: Dict[str, str]) -> int:
                mid = m["id"].lower()
                if "gemini-3.1-flash-lite" in mid:
                    return 0
                if "gemini-3-flash-preview" in mid:
                    return 1
                if "gemma-4-26b" in mid:
                    return 2
                if "gemini-3.8-flash" in mid:
                    return 3
                if "gemini" in mid:
                    return 4
                if "gpt-oss-120b" in mid:
                    return 0
                if "gpt-oss-20b" in mid or "qwen3.8" in mid:
                    return 1
                if "gpt-4o" in mid:
                    return 0
                if "grok" in mid:
                    return 1
                if "deepseek" in mid:
                    return 1
                return 10

            model_items.sort(key=sort_key)
            return model_items[:50]
    except Exception as exc:
        logger.warning("Exception fetching models from %s: %s", models_url, exc)
        return []


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
    provider = data.get("ai_provider", "openrouter")
    def_base, def_model = get_provider_defaults(provider)

    from ..prompts import default_prompts

    try:
        temp_val = float(data.get("ai_temperature", default_prompts.DEFAULT_TEMPERATURE))
    except (ValueError, TypeError):
        temp_val = default_prompts.DEFAULT_TEMPERATURE

    try:
        max_tokens_val = int(data.get("ai_max_tokens", default_prompts.DEFAULT_MAX_TOKENS))
    except (ValueError, TypeError):
        max_tokens_val = default_prompts.DEFAULT_MAX_TOKENS

    return {
        "bot_token": data.get("telegram_bot_token", ""),
        "group_id": data.get("telegram_group_id", ""),
        "ai_provider": provider,
        "ai_api_key": api_key,
        "ai_base_url": data.get("ai_base_url") or def_base,
        "ai_model": data.get("ai_model") or def_model,
        "ai_system_prompt": data.get("ai_system_prompt") if data.get("ai_system_prompt") is not None else default_prompts.DEFAULT_SYSTEM_PROMPT,
        "ai_persona_anchor": data.get("ai_persona_anchor") if data.get("ai_persona_anchor") is not None else default_prompts.DEFAULT_PERSONA_ANCHOR,
        "ai_followup_anchor": data.get("ai_followup_anchor") if data.get("ai_followup_anchor") is not None else default_prompts.DEFAULT_FOLLOWUP_ANCHOR,
        "ai_temperature": temp_val,
        "ai_max_tokens": max_tokens_val,
        "bot_enabled": data.get("telegram_bot_enabled", "true").lower() in ("true", "1", "yes"),
        "has_token": bool(data.get("telegram_bot_token")),
        "has_ai": bool(api_key),
        # Automated Event Triggers & Prompts
        "notify_top1_enabled": data.get("notify_top1_enabled", "true").lower() in ("true", "1", "yes"),
        "notify_top1_prompt": data.get("notify_top1_prompt") if data.get("notify_top1_prompt") is not None else default_prompts.DEFAULT_NOTIFY_TOP1_PROMPT,
        "notify_new_assignment_enabled": data.get("notify_new_assignment_enabled", "true").lower() in ("true", "1", "yes"),
        "notify_new_assignment_prompt": data.get("notify_new_assignment_prompt") if data.get("notify_new_assignment_prompt") is not None else default_prompts.DEFAULT_NOTIFY_NEW_ASSIGNMENT_PROMPT,
        "notify_deadline_enabled": data.get("notify_deadline_enabled", "true").lower() in ("true", "1", "yes"),
        "notify_deadline_prompt": data.get("notify_deadline_prompt") if data.get("notify_deadline_prompt") is not None else default_prompts.DEFAULT_NOTIFY_DEADLINE_PROMPT,
        "notify_overdue_pv_enabled": data.get("notify_overdue_pv_enabled", "true").lower() in ("true", "1", "yes"),
        "notify_overdue_pv_prompt": data.get("notify_overdue_pv_prompt") if data.get("notify_overdue_pv_prompt") is not None else default_prompts.DEFAULT_NOTIFY_OVERDUE_PV_PROMPT,
        "notify_overdue_group_enabled": data.get("notify_overdue_group_enabled", "true").lower() in ("true", "1", "yes"),
        "notify_overdue_group_prompt": data.get("notify_overdue_group_prompt") if data.get("notify_overdue_group_prompt") is not None else default_prompts.DEFAULT_NOTIFY_OVERDUE_GROUP_PROMPT,
    }


def reset_bot_prompts(db: Session) -> Dict[str, Any]:
    """Reset AI system prompt and anchors back to default prompts."""
    from ..prompts import default_prompts
    set_bot_setting(db, "ai_system_prompt", default_prompts.DEFAULT_SYSTEM_PROMPT)
    set_bot_setting(db, "ai_persona_anchor", default_prompts.DEFAULT_PERSONA_ANCHOR)
    set_bot_setting(db, "ai_followup_anchor", default_prompts.DEFAULT_FOLLOWUP_ANCHOR)
    set_bot_setting(db, "ai_temperature", str(default_prompts.DEFAULT_TEMPERATURE))
    set_bot_setting(db, "ai_max_tokens", str(default_prompts.DEFAULT_MAX_TOKENS))
    # Reset event prompts to defaults
    set_bot_setting(db, "notify_top1_enabled", "true")
    set_bot_setting(db, "notify_top1_prompt", default_prompts.DEFAULT_NOTIFY_TOP1_PROMPT)
    set_bot_setting(db, "notify_new_assignment_enabled", "true")
    set_bot_setting(db, "notify_new_assignment_prompt", default_prompts.DEFAULT_NOTIFY_NEW_ASSIGNMENT_PROMPT)
    set_bot_setting(db, "notify_deadline_enabled", "true")
    set_bot_setting(db, "notify_deadline_prompt", default_prompts.DEFAULT_NOTIFY_DEADLINE_PROMPT)
    set_bot_setting(db, "notify_overdue_pv_enabled", "true")
    set_bot_setting(db, "notify_overdue_pv_prompt", default_prompts.DEFAULT_NOTIFY_OVERDUE_PV_PROMPT)
    set_bot_setting(db, "notify_overdue_group_enabled", "true")
    set_bot_setting(db, "notify_overdue_group_prompt", default_prompts.DEFAULT_NOTIFY_OVERDUE_GROUP_PROMPT)
    return get_all_bot_settings(db)


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


def save_chat_history(
    db: Session,
    chat_id: int,
    role: str,
    content: str,
    user_id: Optional[int] = None,
) -> None:
    """Save a chat message to history and prune old messages beyond the limit."""
    try:
        msg = models.TelegramChatHistory(
            chat_id=chat_id,
            user_id=user_id,
            role=role,
            content=content,
            created_at=datetime.utcnow(),
        )
        db.add(msg)
        db.commit()

        # Prune older messages if exceeding 25 per chat
        count = (
            db.query(models.TelegramChatHistory)
            .filter(models.TelegramChatHistory.chat_id == chat_id)
            .count()
        )
        if count > 25:
            oldest_ids = (
                db.query(models.TelegramChatHistory.id)
                .filter(models.TelegramChatHistory.chat_id == chat_id)
                .order_by(models.TelegramChatHistory.created_at.asc())
                .limit(count - 25)
                .all()
            )
            to_delete = [r[0] for r in oldest_ids]
            if to_delete:
                db.query(models.TelegramChatHistory).filter(
                    models.TelegramChatHistory.id.in_(to_delete)
                ).delete(synchronize_session=False)
                db.commit()
    except Exception as exc:
        logger.warning("Failed to save telegram chat history: %s", exc)


def clear_chat_history(db: Session, chat_id: Optional[int] = None) -> int:
    """Clear chat history for a specific chat or across all chats to eliminate memory latency."""
    try:
        q = db.query(models.TelegramChatHistory)
        if chat_id is not None:
            q = q.filter(models.TelegramChatHistory.chat_id == chat_id)
        count = q.delete(synchronize_session=False)
        db.commit()
        return count
    except Exception as exc:
        logger.warning("Failed to clear telegram chat history: %s", exc)
        db.rollback()
        return 0


def get_chat_history(
    db: Session,
    chat_id: int,
    limit: int = 12,
) -> List[Dict[str, str]]:
    """Retrieve recent conversation history formatted for OpenAI/OpenRouter messages list."""
    try:
        rows = (
            db.query(models.TelegramChatHistory)
            .filter(models.TelegramChatHistory.chat_id == chat_id)
            .order_by(models.TelegramChatHistory.created_at.desc())
            .limit(limit)
            .all()
        )
        rows.reverse()
        return [{"role": r.role, "content": r.content} for r in rows]
    except Exception as exc:
        logger.warning("Failed to get telegram chat history: %s", exc)
        return []


def is_recent_conversation(
    db: Session,
    chat_id: int,
    max_idle_minutes: int = 120,
) -> bool:
    """Check if the last message in this chat was sent within max_idle_minutes."""
    try:
        last_msg = (
            db.query(models.TelegramChatHistory)
            .filter(models.TelegramChatHistory.chat_id == chat_id)
            .order_by(models.TelegramChatHistory.created_at.desc())
            .first()
        )
        if not last_msg:
            return False
        diff = (datetime.utcnow() - last_msg.created_at).total_seconds() / 60.0
        return diff <= max_idle_minutes
    except Exception:
        return False


def format_telegram_html(text: str) -> str:
    """Format and sanitize AI output for Telegram HTML parse_mode.

    1. Converts markdown code blocks (```python ... ```) to <pre><code>...</code></pre>.
    2. Converts markdown headers (### Title) to <b>Title</b>.
    3. Converts markdown bullets (* or -) to clean emoji bullets (🔹).
    4. Converts bold markdown (**text** or __text__) to <b>text</b>.
    5. Converts inline code (`code`) to <code>code</code>.
    6. Converts single asterisk italics (*text* or _text_) to <i>text</i>.
    7. Converts markdown links [text](url) to <a href="url">text</a>.
    8. Strips any stray remaining asterisks or underscores so no ugly markdown shows up.
    9. Escapes raw < and > while preserving valid Telegram tags (b, i, u, s, code, pre, a, blockquote).
    """
    if not text:
        return ""

    # Normalize linebreaks
    text = text.replace("\r\n", "\n")

    # 1. Convert code blocks: ```lang ... ``` -> <pre><code>...</code></pre>
    text = re.sub(r'```([a-zA-Z0-9_]*)\n?(.*?)```', r'<pre><code>\2</code></pre>', text, flags=re.DOTALL)

    # 2. Convert headers like ### Title -> <b>Title</b>
    text = re.sub(r'^(?:#{1,6})\s+(.+)$', r'<b>\1</b>', text, flags=re.MULTILINE)

    # 3. Convert bullet points: * Item or - Item -> 🔹 Item
    text = re.sub(r'^\s*[\*\-]\s+(.+)$', r'🔹 \1', text, flags=re.MULTILINE)

    # 4. Convert bold: **text** or ***text*** or __text__ -> <b>text</b>
    text = re.sub(r'\*{2,3}([^\*\n]+?)\*{2,3}', r'<b>\1</b>', text)
    text = re.sub(r'_{2}([^\_\n]+?)_{2}', r'<b>\1</b>', text)

    # 5. Convert inline code: `code` -> <code>code</code>
    text = re.sub(r'`([^`\n]+)`', r'<code>\1</code>', text)

    # 6. Convert markdown links: [label](url) -> <a href="url">label</a>
    text = re.sub(r'\[([^\]]+)\]\((https?://[^\)]+)\)', r'<a href="\2">\1</a>', text)

    # 7. Convert italic: *text* or _text_ -> <i>text</i>
    text = re.sub(r'(?<!\*)\*([^\*\n]+?)\*(?!\*)', r'<i>\1</i>', text)
    text = re.sub(r'(?<![a-zA-Z0-9_])_([^\_\n]+?)_(?![a-zA-Z0-9_])', r'<i>\1</i>', text)

    # 8. Remove any remaining stray asterisks
    text = re.sub(r'\*{1,}', '', text)

    tag_regex = re.compile(
        r'(</?(?:b|strong|i|em|u|ins|s|strike|del|code|pre|a|blockquote)(?:\s+href="[^"]*")?\s*>)',
        re.IGNORECASE,
    )
    parts = tag_regex.split(text)
    for i in range(0, len(parts), 2):
        # Escape raw < and > in the text segments outside of tags
        parts[i] = parts[i].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    return "".join(parts).strip()


def is_private_telegram_chat(chat_id: Any) -> bool:
    """Check if chat_id represents a Telegram private chat (positive integer)."""
    if not chat_id:
        return False
    try:
        s = str(chat_id).strip()
        if s.startswith("-"):
            return False
        return int(s) > 0
    except (ValueError, TypeError):
        return False


async def mirror_pv_to_owner(
    telegram_id: Any,
    telegram_username: Optional[str] = None,
    user_info: Optional[str] = None,
    text: str = "",
    direction: str = "inbound",  # "inbound" | "outbound" | "action"
    token: Optional[str] = None,
    db: Optional[Session] = None,
) -> bool:
    """Mirror any private chat message or action between a user and the bot to the Owner's PV."""
    if not is_private_telegram_chat(telegram_id):
        return False

    session_to_close = None
    if db is None:
        from ..database import SessionLocal
        session_to_close = SessionLocal()
        session = session_to_close
    else:
        session = db

    try:
        owner_chat_id = get_owner_chat_id(session)
        if not owner_chat_id:
            return False

        # Crucial safeguard: Never mirror owner's own interactions to the owner
        if str(telegram_id).strip() == str(owner_chat_id).strip():
            return False

        # Look up user if user_info not fully resolved
        if not user_info:
            try:
                t_id_int = int(str(telegram_id).strip())
                u = session.query(models.User).filter(models.User.telegram_id == t_id_int).first()
                if u:
                    if models.is_owner(u):
                        return False  # Owner account
                    role_fa = "مدیر مدرسه" if u.is_admin else "دانش‌آموز"
                    fname = getattr(u, "full_name", None)
                    display_name = f"{fname} ({u.username})" if fname else u.username
                    user_info = f"<b>{display_name}</b> [{role_fa}]"
                    if not telegram_username and u.telegram_username:
                        telegram_username = u.telegram_username
            except Exception:
                pass

        if not user_info:
            user_info = "<i>متصل‌نشده به حساب اپ</i>"

        if not token:
            token = get_bot_setting(session, "telegram_bot_token")
    finally:
        if session_to_close:
            session_to_close.close()

    if not token or not owner_chat_id:
        return False

    # Choose icon & direction header
    if direction == "inbound":
        header_title = "📩 <b>پیام دریافتی از کاربر در پیوی</b>"
    elif direction == "outbound":
        header_title = "🤖 <b>پاسخ ارسالی ربات به کاربر در پیوی</b>"
    elif direction == "action":
        header_title = "🔘 <b>عملیات کاربر در پیوی</b>"
    else:
        header_title = "💬 <b>مکالمه در پیوی</b>"

    tg_user_str = f" (@{telegram_username})" if telegram_username else ""

    clean_body = (text or "").strip()
    if len(clean_body) > 3500:
        clean_body = clean_body[:3450] + "\n... [متن طولانی کوتاه شد]"

    mirror_msg = (
        f"{header_title}\n"
        f"👤 <b>کاربر در اپ:</b> {user_info}\n"
        f"🆔 <b>آیدی تلگرام:</b> <code>{telegram_id}</code>{tg_user_str}\n"
        f"────────────────────\n"
        f"{clean_body}"
    )

    return await send_telegram_message(
        token=token,
        chat_id=owner_chat_id,
        text=mirror_msg,
        parse_mode="HTML",
        mirror_pv=False,
    )


async def _async_mirror_outbound(token: str, target_chat_id: Any, text: str) -> None:
    """Internal fire-and-forget task to mirror outbound PV messages to Owner."""
    try:
        await mirror_pv_to_owner(
            telegram_id=target_chat_id,
            text=text,
            direction="outbound",
            token=token,
        )
    except Exception as exc:
        logger.debug("Failed outbound PV mirror to owner: %s", exc)


async def send_telegram_message_get_id(
    token: str,
    chat_id: str | int,
    text: str,
    parse_mode: str = "HTML",
    reply_to_message_id: Optional[int] = None,
    reply_markup: Optional[Dict[str, Any]] = None,
    mirror_pv: bool = True,
) -> Optional[int]:
    """Send a message via Telegram Bot HTTP API and return message_id if successful."""
    if not token or not chat_id:
        return None

    # Sanitize and convert markdown to valid Telegram HTML if in HTML mode
    formatted_text = format_telegram_html(text) if parse_mode == "HTML" else text

    url = f"{TELEGRAM_API_BASE.format(token=token)}/sendMessage"
    payload: Dict[str, Any] = {
        "chat_id": chat_id,
        "text": formatted_text,
        "parse_mode": parse_mode,
    }
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                msg_id = data.get("result", {}).get("message_id")
                if mirror_pv and is_private_telegram_chat(chat_id):
                    asyncio.create_task(_async_mirror_outbound(token, chat_id, text))
                return msg_id
            logger.warning("Telegram sendMessage error: %s %s", resp.status_code, resp.text)

            # Fallback: if Telegram rejected the HTML entities, send as clean plain text
            if parse_mode:
                plain_payload = dict(payload)
                plain_payload.pop("parse_mode", None)
                # Strip HTML tags for clean fallback
                plain_payload["text"] = re.sub(r'<[^>]+>', '', formatted_text)
                fallback_resp = await client.post(url, json=plain_payload)
                if fallback_resp.status_code == 200:
                    fb_data = fallback_resp.json()
                    msg_id = fb_data.get("result", {}).get("message_id")
                    logger.info("Telegram message sent successfully using plain-text fallback")
                    if mirror_pv and is_private_telegram_chat(chat_id):
                        asyncio.create_task(_async_mirror_outbound(token, chat_id, text))
                    return msg_id
    except Exception as exc:
        logger.error("Failed to send Telegram message: %s", exc)
    return None


async def send_telegram_message(
    token: str,
    chat_id: str | int,
    text: str,
    parse_mode: str = "HTML",
    reply_to_message_id: Optional[int] = None,
    reply_markup: Optional[Dict[str, Any]] = None,
    mirror_pv: bool = True,
) -> bool:
    """Send a message via Telegram Bot HTTP API with automatic HTML sanitization, fallback and Owner PV mirroring."""
    msg_id = await send_telegram_message_get_id(
        token=token,
        chat_id=chat_id,
        text=text,
        parse_mode=parse_mode,
        reply_to_message_id=reply_to_message_id,
        reply_markup=reply_markup,
        mirror_pv=mirror_pv,
    )
    return msg_id is not None


async def delete_telegram_message(token: str, chat_id: str | int, message_id: int) -> bool:
    """Delete a Telegram message."""
    if not token or not chat_id or not message_id:
        return False
    url = f"{TELEGRAM_API_BASE.format(token=token)}/deleteMessage"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json={"chat_id": chat_id, "message_id": message_id})
            return resp.status_code == 200
    except Exception as exc:
        logger.warning("Failed to delete Telegram message %s in chat %s: %s", message_id, chat_id, exc)
        return False


async def send_chat_action(token: str, chat_id: str | int, action: str = "typing") -> bool:
    """Send chat action (e.g. typing) to indicate bot is working on a response."""
    if not token or not chat_id:
        return False
    url = f"{TELEGRAM_API_BASE.format(token=token)}/sendChatAction"
    try:
        from .ai_agent import get_shared_client
        client = get_shared_client()
        resp = await client.post(url, json={"chat_id": chat_id, "action": action}, timeout=3.0)
        return resp.status_code == 200
    except Exception:
        return False


async def edit_telegram_message(
    token: str,
    chat_id: str | int,
    message_id: int,
    text: str,
    reply_markup: Optional[Dict[str, Any]] = None,
    parse_mode: str = "HTML",
    mirror_pv: bool = True,
) -> bool:
    """Edit an existing Telegram message (for step-by-step button wizards)."""
    if not token or not chat_id or not message_id:
        return False

    formatted_text = format_telegram_html(text) if parse_mode == "HTML" else text
    url = f"{TELEGRAM_API_BASE.format(token=token)}/editMessageText"
    payload: Dict[str, Any] = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": formatted_text,
        "parse_mode": parse_mode,
    }
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                if mirror_pv and is_private_telegram_chat(chat_id):
                    asyncio.create_task(_async_mirror_outbound(token, chat_id, f"🔄 [ویرایش پیام/ویزارد]:\n{text}"))
                return True
            logger.warning("Telegram editMessageText error: %s %s", resp.status_code, resp.text)
            if parse_mode:
                plain_payload = dict(payload)
                plain_payload.pop("parse_mode", None)
                plain_payload["text"] = re.sub(r'<[^>]+>', '', formatted_text)
                fallback_resp = await client.post(url, json=plain_payload)
                if fallback_resp.status_code == 200:
                    if mirror_pv and is_private_telegram_chat(chat_id):
                        asyncio.create_task(_async_mirror_outbound(token, chat_id, f"🔄 [ویرایش پیام/ویزارد]:\n{text}"))
                    return True
                return False
    except Exception as exc:
        logger.error("Failed to edit Telegram message: %s", exc)
    return False


async def answer_callback_query(
    token: str,
    callback_query_id: str,
    text: Optional[str] = None,
    show_alert: bool = False,
) -> bool:
    """Acknowledge a Telegram inline button tap."""
    if not token or not callback_query_id:
        return False

    url = f"{TELEGRAM_API_BASE.format(token=token)}/answerCallbackQuery"
    payload: Dict[str, Any] = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
        payload["show_alert"] = show_alert

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(url, json=payload)
            return resp.status_code == 200
    except Exception as exc:
        logger.error("Failed to answer callback query: %s", exc)
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
    notify_enabled = get_bot_setting(db, "notify_top1_enabled", "true").lower() in ("true", "1")

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

            if not notify_enabled:
                return top_username

            from . import ai_agent
            ctx = {
                "event": "top1_change",
                "new_leader": top_username,
                "previous_leader": last_top_name,
                "completion_percentage": percentage,
                "current_streak": streak,
            }
            ai_text = await ai_agent.generate_ai_event_text(db, "top1", ctx)
            announcement = ai_text or (
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


async def broadcast_deadline_announcement(
    db: Session,
    assignment: models.Assignment,
    hours_left: float,
) -> bool:
    """Send approaching deadline warning to the Telegram group."""
    token = get_bot_setting(db, "telegram_bot_token")
    group_id = get_bot_setting(db, "telegram_group_id")
    enabled = get_bot_setting(db, "telegram_bot_enabled", "true").lower() in ("true", "1")
    notify_enabled = get_bot_setting(db, "notify_deadline_enabled", "true").lower() in ("true", "1")

    if not token or not group_id or not enabled or not notify_enabled:
        return False

    import math
    from . import school_knowledge

    subj_info = school_knowledge.resolve_subject(assignment.subject_id or assignment.course or "")
    teacher = f" (استاد {subj_info['teacher']})" if subj_info else ""
    subj_name = subj_info["name"] if subj_info else (assignment.subject_id or "عمومی")

    if hours_left < 1:
        minutes = max(1, math.ceil(hours_left * 60))
        time_text = f"کمتر از <b>{minutes} دقیقه</b>"
        urgency = "🚨 <b>فوری: ددلاین در یک‌قدمی پایان!</b> ⏰🔥"
    elif hours_left <= 2:
        time_text = f"فقط <b>{math.ceil(hours_left)} ساعت</b>"
        urgency = "⚠️ <b>هشدار ددلاین: فقط چند ساعت مانده!</b> ⚡"
    else:
        time_text = f"حدود <b>{math.ceil(hours_left)} ساعت</b> (فردا)"
        urgency = "📢 <b>یادآوری موعد تحویل تکلیف</b> 📚"

    from . import ai_agent
    ctx = {
        "event": "deadline_reminder",
        "assignment_title": assignment.title,
        "subject": f"{subj_name}{teacher}",
        "hours_left": hours_left,
        "time_text": time_text,
    }
    ai_text = await ai_agent.generate_ai_event_text(db, "deadline", ctx)
    text = ai_text or (
        f"{urgency}\n\n"
        f"🔹 <b>تکلیف:</b> {assignment.title}\n"
        f"🔹 <b>درس:</b> {subj_name}{teacher}\n"
        f"🔹 <b>فرصت باقیمانده:</b> {time_text}\n\n"
        f"بچه‌ها حواستون باشه استریک‌هاتون نسوزه! تکالیفتون رو به موقع انجام بدید و تیک بزنید 💪\n"
        f"<i>(برای مشاهده جزئیات و دانلود فایل‌ها، اپلیکیشن ArchSchool رو باز کنید 📱)</i>"
    )

    return await send_telegram_message(token, group_id, text)


async def broadcast_new_assignment(
    db: Session,
    assignment: models.Assignment,
) -> bool:
    """Send immediate new assignment alert to the Telegram supergroup."""
    token = get_bot_setting(db, "telegram_bot_token")
    group_id = get_bot_setting(db, "telegram_group_id")
    enabled = get_bot_setting(db, "telegram_bot_enabled", "true").lower() in ("true", "1")
    notify_enabled = get_bot_setting(db, "notify_new_assignment_enabled", "true").lower() in ("true", "1")

    if not token or not group_id or not enabled or not notify_enabled:
        return False

    from . import school_knowledge
    subj_info = school_knowledge.resolve_subject(assignment.subject_id or assignment.course or "")
    teacher = f" (استاد {subj_info['teacher']})" if subj_info else ""
    subj_name = subj_info["name"] if subj_info else (assignment.subject_id or "عمومی")

    due_str = "بدون مهلت تحویل"
    if assignment.due_date:
        due_str = school_knowledge.format_iran_datetime(assignment.due_date)

    is_reminder = getattr(assignment, "is_reminder_only", False)
    header = "📌 <b>یادآوری جدید کلاس ثبت شد!</b>" if is_reminder else "📢 <b>تکلیف جدید در اپلیکیشن ثبت شد!</b> 📚🔥"

    from . import ai_agent
    ctx = {
        "event": "new_assignment",
        "assignment_title": assignment.title,
        "subject": f"{subj_name}{teacher}",
        "due_date": due_str,
        "description": assignment.description or "",
        "is_reminder_only": is_reminder,
    }
    ai_text = await ai_agent.generate_ai_event_text(db, "new_assignment", ctx)

    if ai_text:
        text = ai_text
    else:
        text = (
            f"{header}\n\n"
            f"🔹 <b>عنوان:</b> {assignment.title}\n"
            f"🔹 <b>درس:</b> {subj_name}{teacher}\n"
            f"⏰ <b>مهلت تحویل:</b> {due_str}\n"
        )
        if is_reminder:
            text += "<i>(این مورد فقط جهت یادآوری ثبت شده و نیاز به تیک زدن ندارد)</i>\n\n"
        else:
            text += "\nبچه‌ها سریع دست‌به‌کار بشید و تیکش رو بزنید تا استریک‌تون پرواز کنه! 🚀⚡\n"

        text += "📱 <i>مشاهده پیوست‌ها و جزئیات در اپلیکیشن ArchSchool</i>"

    return await send_telegram_message(token, group_id, text)


def build_owner_overdue_audit_report(
    assignments: List[Tuple[models.Assignment, str, str]],
    all_uncompleted_users: Dict[int, models.User],
    pv_sent_users: List[Tuple[str, int]],
    skipped_users: List[Tuple[str, int]],
    group_sent: bool,
    skipped_overflow: bool,
) -> str:
    from . import school_knowledge
    now_iran = (datetime.utcnow() + timedelta(hours=3.5)).strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "🛡️ <b>گزارش لحظه‌ای پیگیری تکالیف منقضی (Owner Live Audit)</b> 📊",
        "────────────────────",
        f"🕒 <b>زمان اجرا:</b> <code>{now_iran}</code>",
        f"📋 <b>تعداد تکالیف منقضی بررسی‌شده:</b> <b>{len(assignments)}</b> مورد",
    ]
    for asgn, subj, tch in assignments:
        due_str = school_knowledge.format_iran_datetime(asgn.due_date) if asgn.due_date else "گذشته"
        lines.append(f"  ▫️ <b>{asgn.title}</b> ({subj}{tch}) - موعد: {due_str}")

    lines.append("────────────────────")
    if skipped_overflow:
        lines.append("⚠️ <b>تصمیم هوشمند سیستم (قانون اپلیکیشن):</b>")
        lines.append(
            f"تعداد تکالیف منقضی به <b>{len(assignments)} مورد (≥ ۴)</b> رسید؛ "
            "دقیقاً مطابق رفتار اپلیکیشن، ربات از ارسال پیام یادآوری و تگ در گروه صرف‌نظر کرد (بی‌خیال شد) "
            "تا از اسپم چت جلوگیری شود و تکالیف به بخش منقضی‌ها منتقل شدند."
        )
    else:
        lines.append("📊 <b>تصمیم سیستم:</b>")
        lines.append("تعداد تکالیف کمتر از ۴ مورد است؛ فرآیند پیگیری فعال شد.")
        lines.append("")
        lines.append(f"📢 <b>اطلاع‌رسانی در گروه:</b> {'✅ ارسال شد (فقط تگ کردن بچه‌ها برای مراجعه به پیوی)' if group_sent else '❌ ارسال نشد یا گروه متصل نیست'}")
        lines.append(f"💬 <b>پیام خصوصی (PV) به دانش‌آموزان:</b>")
        if pv_sent_users:
            for uname, tcount in pv_sent_users:
                lines.append(f"  ▫️ کاربر <b>{uname}</b>: {tcount} تکلیف ناتمام ➔ پیام پیوی + دکمه‌های تیک‌زنی ارسال شد ✅")
        else:
            lines.append("  ▫️ هیچ پیام خصوصی ارسال نشد (یا آیدی تلگرام متصل نیست)")
        if skipped_users:
            for uname, tcount in skipped_users:
                lines.append(f"  ▫️ کاربر <b>{uname}</b>: {tcount} تکلیف (≥ ۴) ➔ طبق قانون اپ نادیده گرفته شد ⏭️")

    lines.append("────────────────────")
    lines.append("⚡ <i>این گزارش جهت اطلاع لحظه‌ای مدیریت ارشد به پیوی شما ارسال گردید.</i>")
    return "\n".join(lines)


async def process_overdue_assignments(db: Session, force: bool = False) -> int:
    """Find newly expired assignments and send ONE combined message to the group
    tagging incomplete students, and ONE private follow-up message to each student.
    Enforces the app rule: if overdue tasks >= 4, skips prompting to avoid spam.
    Dispatches a real-time audit report directly to Owner's Telegram PV.
    """
    token = get_bot_setting(db, "telegram_bot_token")
    group_id = get_bot_setting(db, "telegram_group_id")
    owner_chat_id = get_owner_chat_id(db) or get_bot_setting(db, "owner_telegram_chat_id")
    enabled = get_bot_setting(db, "telegram_bot_enabled", "true").lower() in ("true", "1")
    if not token or not enabled:
        return 0

    pv_enabled = get_bot_setting(db, "notify_overdue_pv_enabled", "true").lower() in ("true", "1")
    group_enabled = get_bot_setting(db, "notify_overdue_group_enabled", "true").lower() in ("true", "1")

    if not pv_enabled and not group_enabled:
        return 0

    from . import ai_agent, school_knowledge
    from sqlalchemy import or_

    candidates = (
        db.query(models.Assignment)
        .filter(
            models.Assignment.deleted_at.is_(None),
            or_(
                models.Assignment.is_reminder_only.is_(False),
                models.Assignment.is_reminder_only.is_(None),
            ),
            models.Assignment.due_date.isnot(None),
        )
        .order_by(models.Assignment.due_date.asc())
        .all()
    )

    overdue_assignments = [
        asgn for asgn in candidates
        if school_knowledge.is_assignment_overdue(asgn.due_date, asgn.subject_id)
    ]

    new_overdue_assignments = []
    for asgn in overdue_assignments:
        existing = (
            db.query(models.OverdueFollowupNotification)
            .filter(models.OverdueFollowupNotification.assignment_id == asgn.id)
            .first()
        )
        if existing and not force:
            continue
        new_overdue_assignments.append(asgn)

    if not new_overdue_assignments:
        return 0

    user_to_assignments: Dict[int, List[Tuple[models.Assignment, str]]] = {}
    all_uncompleted_users: Dict[int, models.User] = {}
    assignment_items: List[Tuple[models.Assignment, str, str]] = []
    assignments_to_mark: List[models.Assignment] = []

    for asgn in new_overdue_assignments:
        assignments_to_mark.append(asgn)

        completed_user_ids = {
            row[0]
            for row in db.query(models.AssignmentCompletion.user_id)
            .filter(models.AssignmentCompletion.assignment_id == asgn.id)
            .all()
        }

        q_users = db.query(models.User).filter(models.User.is_active.is_(True))
        if completed_user_ids:
            q_users = q_users.filter(~models.User.id.in_(completed_user_ids))
        uncompleted_for_this = q_users.all()

        subj_info = school_knowledge.resolve_subject(asgn.subject_id or asgn.course or "")
        teacher = f" (استاد {subj_info['teacher']})" if subj_info else ""
        subj_name = subj_info["name"] if subj_info else (asgn.subject_id or "عمومی")
        assignment_items.append((asgn, subj_name, teacher))

        if not uncompleted_for_this:
            continue

        for u in uncompleted_for_this:
            all_uncompleted_users[u.id] = u
            if u.id not in user_to_assignments:
                user_to_assignments[u.id] = []
            user_to_assignments[u.id].append((asgn, subj_name))

    # Rule 1: Exactly like the app (home.tsx): if overdue assignments count >= 4, auto-skip / dismiss
    skip_due_to_overflow = len(new_overdue_assignments) >= 4

    pv_sent_users: List[Tuple[str, int]] = []
    skipped_users: List[Tuple[str, int]] = []
    group_sent = False

    if not skip_due_to_overflow:
        # 1. Private chat follow-up: EXACTLY ONE MESSAGE per student listing all their overdue tasks
        if pv_enabled and all_uncompleted_users:
            for u_id, u in all_uncompleted_users.items():
                u_tasks = user_to_assignments.get(u_id, [])
                if not u_tasks:
                    continue

                # App rule check: if this specific student has >= 4 overdue tasks, skip prompting them
                if len(u_tasks) >= 4:
                    skipped_users.append((u.username, len(u_tasks)))
                    continue

                target_chat_id = u.telegram_id
                if not target_chat_id and (models.is_owner(u) or u.id == 1) and owner_chat_id:
                    target_chat_id = owner_chat_id
                    try:
                        u.telegram_id = int(owner_chat_id)
                        db.commit()
                    except Exception:
                        db.rollback()

                if not target_chat_id:
                    continue

                u_tasks_str = "\n".join([f"🔹 <b>{a.title}</b> ({s})" for a, s in u_tasks])
                pv_context = {
                    "event": "overdue_pv",
                    "student_name": u.username,
                    "assignment_title": ", ".join([a.title for a, _ in u_tasks]),
                    "tasks_list": u_tasks_str,
                }
                ai_msg = await ai_agent.generate_ai_event_text(db, "overdue_pv", pv_context)
                if not ai_msg:
                    ai_msg = (
                        f"سلام <b>{u.username}</b> عزیز 👋\n\n"
                        f"⏰ مهلت تحویل تکالیف زیر به پایان رسیده و هنوز تیک آن‌ها را در اپلیکیشن ثبت نکرده‌ای:\n"
                        f"{u_tasks_str}\n\n"
                        f"کدوم رو انجام دادی برات تیک بزنم؟ می‌تونی دکمه‌های زیر رو لمس کنی یا همینجا برام بنویسی تا فوراً برات ثبت کنم! 👇⚡"
                    )

                # Interactive inline buttons for 1-click instant completion
                inline_buttons = []
                for a, s in u_tasks:
                    btn_title = a.title if len(a.title) <= 22 else f"{a.title[:20]}..."
                    inline_buttons.append([{"text": f"✅ تیک زدن {btn_title}", "callback_data": f"task_toggle:{a.id}"}])
                if len(u_tasks) > 1:
                    inline_buttons.append([{"text": "⚡ تیک زدن همه تکالیف", "callback_data": "task_toggle:all"}])

                reply_markup = {"inline_keyboard": inline_buttons} if inline_buttons else None
                try:
                    if await send_telegram_message(token, target_chat_id, ai_msg, reply_markup=reply_markup):
                        pv_sent_users.append((u.username, len(u_tasks)))
                        logger.info("Sent combined overdue PV follow-up with buttons to user %s for %d assignments", u.username, len(u_tasks))
                except Exception as pv_err:
                    logger.warning("Failed to send overdue PV message to user %s: %s", u.id, pv_err)

        # 2. Group callout: ONLY tag the students and tell them to come to PV (no tasks listed in group)
        if group_enabled and group_id and assignment_items and all_uncompleted_users:
            user_mentions = []
            for u in all_uncompleted_users.values():
                if u.telegram_id:
                    user_mentions.append(f'<a href="tg://user?id={u.telegram_id}">{u.username}</a>')
                elif u.telegram_username:
                    user_mentions.append(f"@{u.telegram_username.lstrip('@')}")
                else:
                    user_mentions.append(f"<b>{u.username}</b>")

            tags_str = " ".join(user_mentions) if user_mentions else "بچه‌ها"

            group_context = {
                "event": "overdue_group",
                "incomplete_count": len(all_uncompleted_users),
                "incomplete_tags": tags_str,
            }
            ai_group_msg = await ai_agent.generate_ai_event_text(db, "overdue_group", group_context)
            if not ai_group_msg:
                ai_group_msg = (
                    f"👉 {tags_str}\n\n"
                    f"بچه‌ها سریع بیاید پیوی ربات کارتون دارم! 🏃‍♂️⚡"
                )
            try:
                if await send_telegram_message(token, group_id, ai_group_msg):
                    group_sent = True
                    logger.info("Broadcasted group callout tagging %d users to check PV", len(user_mentions))
            except Exception as grp_err:
                logger.warning("Failed to send overdue group callout: %s", grp_err)

    # Mark all assignments in this batch as processed so they NEVER trigger again
    for asgn in assignments_to_mark:
        existing = (
            db.query(models.OverdueFollowupNotification)
            .filter(models.OverdueFollowupNotification.assignment_id == asgn.id)
            .first()
        )
        if not existing:
            marker = models.OverdueFollowupNotification(assignment_id=asgn.id)
            db.add(marker)
    try:
        db.commit()
        logger.info("Successfully marked %d assignments in overdue_followup_notifications", len(assignments_to_mark))
    except Exception as exc:
        db.rollback()
        logger.error("Failed to commit OverdueFollowupNotification markers: %s", exc)

    # Real-time Audit Report sent directly to Owner's Telegram PV!
    if owner_chat_id:
        audit_report = build_owner_overdue_audit_report(
            assignments=assignment_items,
            all_uncompleted_users=all_uncompleted_users,
            pv_sent_users=pv_sent_users,
            skipped_users=skipped_users,
            group_sent=group_sent,
            skipped_overflow=skip_due_to_overflow,
        )
        try:
            await send_telegram_message(token, owner_chat_id, audit_report)
            logger.info("Dispatched real-time overdue audit report to owner (chat %s)", owner_chat_id)
        except Exception as o_err:
            logger.warning("Could not dispatch overdue audit report to owner: %s", o_err)

    return len(assignments_to_mark)


def is_503_error_content(text: str) -> bool:
    """Check if content indicates a 503 Service Unavailable or overloaded AI response."""
    if not text:
        return False
    lower = text.lower()
    return (
        "503" in lower
        or "سرور ارائه‌دهنده هوش مصنوعی موقتاً با ترافیک بالا مواجه است" in text
        or "ترافیک بالا مواجه است" in text
        or "ترافیک شدید" in text
        or "زیر بار شدید ترافیک" in text
        or "در صف پردازش" in text
        or "service unavailable" in lower
        or "overloaded" in lower
    )


async def resolve_pending_503_chats(db: Session) -> int:
    """Finds all conversations whose last message received a 503 error,
    and delivers the generated answer now using the full 30-attempt retry mechanism.
    Returns the number of resolved chats.
    """
    token = get_bot_setting(db, "telegram_bot_token")
    if not token:
        return 0

    ai_key = get_bot_setting(db, "ai_api_key") or get_bot_setting(db, "gemini_api_key")
    if not ai_key:
        return 0

    from sqlalchemy import func
    from . import ai_agent

    try:
        # Query the latest TelegramChatHistory record for each chat_id
        subq = (
            db.query(
                models.TelegramChatHistory.chat_id,
                func.max(models.TelegramChatHistory.id).label("max_id"),
            )
            .group_by(models.TelegramChatHistory.chat_id)
            .subquery()
        )

        latest_records = (
            db.query(models.TelegramChatHistory)
            .join(subq, models.TelegramChatHistory.id == subq.c.max_id)
            .all()
        )
    except Exception as q_err:
        logger.warning("Could not query pending 503 records: %s", q_err)
        return 0

    resolved_count = 0
    provider = get_bot_setting(db, "ai_provider", "openrouter")
    def_base, def_model = get_provider_defaults(provider)
    base_url = get_bot_setting(db, "ai_base_url") or def_base
    model_name = get_bot_setting(db, "ai_model") or def_model

    for record in latest_records:
        chat_id = record.chat_id
        # Check if the latest message was an assistant 503 error or left in queue
        if record.role == "assistant" and is_503_error_content(record.content):
            # Find the user question right before this failed response
            user_msg = (
                db.query(models.TelegramChatHistory)
                .filter(
                    models.TelegramChatHistory.chat_id == chat_id,
                    models.TelegramChatHistory.id < record.id,
                    models.TelegramChatHistory.role == "user",
                )
                .order_by(models.TelegramChatHistory.id.desc())
                .first()
            )
            if not user_msg or not user_msg.content:
                continue

            user_prompt = user_msg.content
            target_user = None
            if user_msg.user_id:
                target_user = db.query(models.User).filter(models.User.id == user_msg.user_id).first()
            elif record.user_id:
                target_user = db.query(models.User).filter(models.User.id == record.user_id).first()

            logger.info("Resolving pending 503 for chat %s (prompt: %s)", chat_id, user_prompt[:50])

            # Fetch compact conversation history excluding the failed assistant message
            history = (
                db.query(models.TelegramChatHistory)
                .filter(
                    models.TelegramChatHistory.chat_id == chat_id,
                    models.TelegramChatHistory.id < record.id,
                )
                .order_by(models.TelegramChatHistory.id.desc())
                .limit(6)
                .all()
            )
            history.reverse()
            conv_history = [{"role": h.role, "content": h.content} for h in history]

            # Indicate typing in chat
            await send_chat_action(token, chat_id, "typing")

            ai_reply, ai_meta = await ai_agent.ask_universal_ai_agent(
                user_prompt=user_prompt,
                api_key=ai_key,
                db=db,
                base_url=base_url,
                model_name=model_name,
                current_user=target_user,
                conversation_history=conv_history,
                is_recent=False,
            )

            # Check if resolution succeeded (not another 503 error)
            if not is_503_error_content(ai_reply):
                formatted_reply = (
                    "🔄 <b>پاسخ به سوال شما (پس از برطرف شدن ترافیک سرور):</b>\n\n"
                    f"{ai_reply}"
                )
                sent = await send_telegram_message(token, chat_id, formatted_reply)
                if sent:
                    save_chat_history(
                        db, chat_id, role="assistant", content=formatted_reply,
                        user_id=target_user.id if target_user else None
                    )
                    resolved_count += 1
                    logger.info("Successfully delivered 503 backlog answer to chat %s", chat_id)

    if resolved_count > 0:
        owner_chat_id = get_bot_setting(db, "owner_telegram_chat_id")
        if owner_chat_id:
            await send_telegram_message(
                token, owner_chat_id,
                f"✅ <b>رسیدگی به پیام‌های معوقه ۵۰۳:</b>\nتعداد <b>{resolved_count}</b> گفتگو که آخرین پیام آن‌ها با خطای ۵۰۳ مواجه شده بود، هم‌اکنون با موفقیت پاسخ داده شدند."
            )

    return resolved_count


async def telegram_automation_daemon(poll_seconds: int = 45) -> None:
    """Continuous automated background worker for ArchSchool Telegram integration.
    Executes periodic checks for newly overdue assignments and Top 1 leaderboard rank shifts.
    Runs continuously throughout application lifespan.
    """
    logger.info("Starting ArchSchool Telegram Automation Daemon (poll interval: %ds)...", poll_seconds)
    await asyncio.sleep(2)

    from ..database import SessionLocal

    # Initial resolution of any pending 503 chats upon startup/deployment
    try:
        with SessionLocal() as db:
            await resolve_pending_503_chats(db)
    except Exception as init_503_err:
        logger.warning("Initial resolve_pending_503_chats failed: %s", init_503_err)

    while True:
        try:
            with SessionLocal() as db:
                try:
                    await process_overdue_assignments(db)
                except Exception as exc:
                    logger.warning("Error processing overdue assignments in daemon: %s", exc)

                try:
                    await check_and_broadcast_top1(db)
                except Exception as exc:
                    logger.warning("Error checking top 1 leaderboard in daemon: %s", exc)

                try:
                    await resolve_pending_503_chats(db)
                except Exception as exc:
                    logger.warning("Error resolving pending 503 chats in daemon: %s", exc)

        except asyncio.CancelledError:
            logger.info("ArchSchool Telegram Automation Daemon cancelled.")
            raise
        except Exception as exc:
            logger.error("Unhandled error in telegram_automation_daemon: %s", exc, exc_info=True)

        await asyncio.sleep(poll_seconds)


async def broadcast_new_assignment_by_id(assignment_id: int) -> bool:
    """Send immediate new assignment alert using a freshly opened DB session."""
    try:
        from ..database import SessionLocal
        with SessionLocal() as db:
            asgn = db.query(models.Assignment).filter(models.Assignment.id == assignment_id).first()
            if asgn:
                return await broadcast_new_assignment(db, asgn)
    except Exception as exc:
        logger.warning("Failed to broadcast assignment by id %s: %s", assignment_id, exc)
    return False


async def broadcast_leaderboard_reset(
    db: Session,
    season_number: int,
    top_entries: List[Dict[str, Any]],
) -> bool:
    """Broadcast the bi-weekly leaderboard reset and season winners to the Telegram supergroup."""
    token = get_bot_setting(db, "telegram_bot_token")
    group_id = get_bot_setting(db, "telegram_group_id")
    enabled = get_bot_setting(db, "telegram_bot_enabled", "true").lower() in ("true", "1")

    if not token or not group_id or not enabled:
        return False

    medals = ["🥇", "🥈", "🥉"]
    winners_text = ""
    for idx, entry in enumerate(top_entries[:3]):
        u_name = entry["user"].username
        pct = round(entry.get("completion_percentage", 0), 1)
        streak = entry.get("current_streak", 0)
        winners_text += f"{medals[idx]} <b>نفر {idx+1}:</b> {u_name} ({pct}% تکمیل · استریک {streak} روز)\n"

    if not winners_text:
        winners_text = "بدون ثبت فعالیت در دوره قبل."

    text = (
        f"🏁 <b>سوت پایان سیزن {season_number} لیدربورد کلاس به صدا درآمد!</b> 🏆👑\n\n"
        f"قهرمانان و رتبه‌های برتر این دوره دو هفته‌ای:\n\n"
        f"{winners_text}\n"
        f"🔥 <b>جدول رنکینگ برای دوره جدید ریست شد!</b>\n"
        f"تمام امتیازها برای سیزن بعدی از صفر آغاز شد. رقابت دو هفته آینده از همین ثانیه شروع شد، ببینم کی صدر جدول رو فتح می‌کنه! 💪⚡\n\n"
        f"📱 <i>مشاهده وضعیت سیزن جدید و تایمر معکوس در اپلیکیشن ArchSchool</i>"
    )
    return await send_telegram_message(token, group_id, text)


# ---------------------------------------------------------------------------
# Telegram Photo & Media Methods
# ---------------------------------------------------------------------------

async def send_telegram_photo(
    token: str,
    chat_id: str | int,
    photo_path: str,
    caption: Optional[str] = None,
    parse_mode: str = "HTML",
    reply_to_message_id: Optional[int] = None,
    reply_markup: Optional[Dict[str, Any]] = None,
) -> bool:
    """Send photo with optional caption and inline keyboard markup."""
    if not token or not chat_id or not os.path.exists(photo_path):
        return False
    url = f"{TELEGRAM_API_BASE.format(token=token)}/sendPhoto"
    data: Dict[str, Any] = {"chat_id": chat_id}
    if caption:
        formatted = format_telegram_html(caption) if parse_mode == "HTML" else caption
        if len(formatted) > 1024:
            formatted = formatted[:1020] + "..."
        data["caption"] = formatted
        if parse_mode:
            data["parse_mode"] = parse_mode
    if reply_to_message_id:
        data["reply_to_message_id"] = reply_to_message_id
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)

    try:
        from .ai_agent import get_shared_client
        client = get_shared_client()
        with open(photo_path, "rb") as f:
            photo_bytes = f.read()

        files = {"photo": (os.path.basename(photo_path), photo_bytes, "image/png")}
        resp = await client.post(url, data=data, files=files, timeout=25.0)
        if resp.status_code == 200:
            if is_private_telegram_chat(chat_id):
                cap_info = f"\nکپشن: {caption}" if caption else ""
                asyncio.create_task(_async_mirror_outbound(token, chat_id, f"📷 [ارسال تصویر / نمودار آماری]{cap_info}"))
            return True
        logger.warning("Telegram sendPhoto error: %s %s", resp.status_code, resp.text[:200])

        # Resilient fallback: If Telegram rejected because of HTML tag parse error, retry plain text
        if resp.status_code == 400 and ("entities" in resp.text.lower() or "parse" in resp.text.lower()):
            clean_data = dict(data)
            clean_data.pop("parse_mode", None)
            clean_data["caption"] = re.sub(r'<[^>]+>', '', data.get("caption", ""))
            files = {"photo": (os.path.basename(photo_path), photo_bytes, "image/png")}
            resp2 = await client.post(url, data=clean_data, files=files, timeout=25.0)
            if resp2.status_code == 200:
                if is_private_telegram_chat(chat_id):
                    cap_info = f"\nکپشن: {clean_data.get('caption')}" if clean_data.get('caption') else ""
                    asyncio.create_task(_async_mirror_outbound(token, chat_id, f"📷 [ارسال تصویر / نمودار آماری]{cap_info}"))
                return True
            logger.warning("Telegram sendPhoto fallback 1 error: %s %s", resp2.status_code, resp2.text[:200])
    except Exception as exc:
        logger.error("Failed to send Telegram photo: %s", exc)
    return False


async def edit_telegram_photo(
    token: str,
    chat_id: str | int,
    message_id: int,
    photo_path: str,
    caption: Optional[str] = None,
    parse_mode: str = "HTML",
    reply_markup: Optional[Dict[str, Any]] = None,
) -> bool:
    """Update an existing photo message in Telegram with new rendered media."""
    if not token or not chat_id or not message_id or not os.path.exists(photo_path):
        return False
    url = f"{TELEGRAM_API_BASE.format(token=token)}/editMessageMedia"
    media_dict: Dict[str, Any] = {
        "type": "photo",
        "media": "attach://photo_file",
    }
    if caption:
        formatted = format_telegram_html(caption) if parse_mode == "HTML" else caption
        if len(formatted) > 1024:
            formatted = formatted[:1020] + "..."
        media_dict["caption"] = formatted
        if parse_mode:
            media_dict["parse_mode"] = parse_mode

    data: Dict[str, Any] = {
        "chat_id": chat_id,
        "message_id": message_id,
        "media": json.dumps(media_dict),
    }
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)

    try:
        from .ai_agent import get_shared_client
        client = get_shared_client()
        with open(photo_path, "rb") as f:
            files = {"photo_file": (os.path.basename(photo_path), f.read(), "image/png")}
            resp = await client.post(url, data=data, files=files, timeout=20.0)
            if resp.status_code == 200:
                return True
            logger.warning("Telegram editMessageMedia error: %s %s", resp.status_code, resp.text[:200])
    except Exception as exc:
        logger.error("Failed to edit Telegram photo: %s", exc)
    return False


# ---------------------------------------------------------------------------
# Owner VIP Reporting & Diagnostics (Error Reports with Code)
# ---------------------------------------------------------------------------

RECENT_SYSTEM_ERRORS: List[Dict[str, Any]] = []
MAX_RECENT_ERRORS = 20


def record_system_error(
    exc: Any,
    endpoint: str = "",
    user_info: str = "",
    context: Optional[dict] = None,
    raw_response: str = "",
    status_code: Optional[int] = None,
) -> Dict[str, Any]:
    """Store in-memory diagnostic error entry with full raw traceback and logs."""
    if isinstance(exc, Exception):
        tb = traceback.format_exc()
        if not tb or tb == "NoneType: None\n":
            tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        err_type = type(exc).__name__
        err_msg = str(exc)
    else:
        tb = str((context or {}).get("traceback") or "") or traceback.format_exc()
        if not tb or tb == "NoneType: None\n":
            tb = "Traceback (most recent call last):\n  [Captured from Service Failure]\n"
        err_type = f"HTTP {status_code}" if status_code else "ServiceError"
        err_msg = str(exc)

    entry = {
        "timestamp": datetime.utcnow(),
        "error_type": err_type,
        "error_msg": err_msg,
        "endpoint": endpoint,
        "user_info": user_info,
        "status_code": status_code,
        "raw_response": raw_response,
        "traceback": tb[-2500:] if len(tb) > 2500 else tb,
        "context": context or {},
    }
    RECENT_SYSTEM_ERRORS.append(entry)
    if len(RECENT_SYSTEM_ERRORS) > MAX_RECENT_ERRORS:
        RECENT_SYSTEM_ERRORS.pop(0)
    return entry


def get_owner_user(db: Session) -> Optional[models.User]:
    """Retrieve system Owner account."""
    owner = db.query(models.User).filter(
        models.User.role == models.ROLE_OWNER,
        models.User.is_active.is_(True),
    ).first()
    if not owner:
        owner = db.query(models.User).filter(
            models.User.is_admin.is_(True),
            models.User.telegram_id.isnot(None),
            models.User.is_active.is_(True),
        ).first()
    return owner


def get_owner_chat_id(db: Session) -> Optional[int]:
    """Resolve Owner's Telegram private chat ID from settings or user profile."""
    explicit = get_bot_setting(db, "owner_telegram_chat_id")
    if explicit and explicit.strip().lstrip("-").isdigit():
        return int(explicit.strip())
    owner = get_owner_user(db)
    if owner and owner.telegram_id:
        return int(owner.telegram_id)
    return None


async def notify_owner_error(
    db: Session,
    exc: Any,
    endpoint: str = "",
    user_info: str = "",
    context: Optional[dict] = None,
    raw_response: str = "",
    status_code: Optional[int] = None,
) -> bool:
    """Send a deeply detailed real-time crash report directly to Owner's Telegram PV."""
    token = get_bot_setting(db, "telegram_bot_token")
    owner_chat_id = get_owner_chat_id(db)
    if not token or not owner_chat_id:
        return False

    entry = record_system_error(exc, endpoint, user_info, context, raw_response, status_code)
    now_str = (entry["timestamp"] + timedelta(hours=3.5)).strftime("%Y-%m-%d %H:%M:%S")

    tb_code = entry["traceback"].strip()
    tb_escaped = tb_code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    raw_block = ""
    if raw_response:
        clean_raw = raw_response.strip().replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")[:1200]
        raw_block = f"\n📄 <b>پاسخ خام سرویس‌دهنده (Raw Response):</b>\n<pre><code class=\"language-json\">{clean_raw}</code></pre>\n"

    status_tag = f" (HTTP {status_code})" if status_code else ""

    msg = (
        f"🚨 <b>گزارش لاگ کامل خطای سیستم (Full Raw Error Log)</b> ⚠️\n\n"
        f"📍 <b>محل وقوع / اندپوینت:</b> <code>{endpoint or 'عملیات سرور'}</code>\n"
        f"👤 <b>کاربر مرتبط:</b> <code>{user_info or 'سیستم / ناشناس'}</code>\n"
        f"🕒 <b>زمان وقوع:</b> <code>{now_str} (ایران)</code>\n\n"
        f"❌ <b>نوع و کد خطا:</b> <code>{entry['error_type']}{status_tag}</code>\n"
        f"💬 <b>پیام خطا:</b> <code>{entry['error_msg']}</code>\n"
        f"{raw_block}\n"
        f"💻 <b>استک تریس و خطوط کد درگیر (Full Traceback):</b>\n"
        f"<pre><code class=\"language-python\">{tb_escaped}</code></pre>\n\n"
        f"💡 <i>این لاگ کامل سیستمی مستقیماً در پیوی مدیریت ارشد ثبت و ارسال گردید.</i>"
    )

    return await send_telegram_message(token, owner_chat_id, msg)


def dispatch_background_owner_error(
    exc: Any,
    endpoint: str = "",
    client_ip: str = "",
    user_info: str = "",
    raw_response: str = "",
    status_code: Optional[int] = None,
) -> None:
    """Fire-and-forget helper to dispatch error notification to Owner."""
    try:
        from ..database import SessionLocal
        def _runner():
            try:
                with SessionLocal() as db:
                    asyncio.run(notify_owner_error(
                        db=db,
                        exc=exc,
                        endpoint=endpoint,
                        user_info=f"{user_info} (IP: {client_ip})" if client_ip else user_info,
                        raw_response=raw_response,
                        status_code=status_code,
                    ))
            except Exception as e:
                logger.warning("Could not dispatch error to owner: %s", e)

        import threading
        threading.Thread(target=_runner, daemon=True).start()
    except Exception as exc2:
        logger.warning("Could not spawn error reporter thread: %s", exc2)


def build_owner_detailed_report(db: Session) -> str:
    """Generate high-detail system audit report for the Owner's private query."""
    import psutil
    from ..ws_manager import manager

    # 1. System Resources
    cpu = psutil.cpu_percent(interval=0.1)
    mem = psutil.virtual_memory()
    mem_used = round(mem.used / (1024 ** 3), 2)
    mem_total = round(mem.total / (1024 ** 3), 2)
    mem_pct = mem.percent

    disk = psutil.disk_usage("/")
    disk_used = round(disk.used / (1024 ** 3), 1)
    disk_total = round(disk.total / (1024 ** 3), 1)

    # 2. Database Stats
    total_users = db.query(models.User).count()
    active_users = db.query(models.User).filter(models.User.is_active.is_(True)).count()
    total_assignments = db.query(models.Assignment).filter(models.Assignment.deleted_at.is_(None)).count()
    ws_conns = len(getattr(manager, "_users", {}))

    # 3. AI & Bot Integration
    provider = get_bot_setting(db, "ai_provider", "openrouter")
    model = get_bot_setting(db, "ai_model", "openai/gpt-4o-mini")
    bot_user = get_bot_setting(db, "telegram_bot_username", "تنظیم‌نشده")

    now_iran = (datetime.utcnow() + timedelta(hours=3.5)).strftime("%Y-%m-%d %H:%M:%S")

    # 4. Error Diagnostics (Full Stacktrace & Logs)
    if RECENT_SYSTEM_ERRORS:
        error_section = f"\n⚠️ <b>لاگ کامل خطاهای اخیر سرور ({len(RECENT_SYSTEM_ERRORS)} مورد اخیر):</b>\n"
        for i, err in enumerate(reversed(RECENT_SYSTEM_ERRORS[-3:])):
            t_str = (err["timestamp"] + timedelta(hours=3.5)).strftime("%H:%M:%S")
            full_tb = err["traceback"].strip().replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            if len(full_tb) > 1400:
                full_tb = full_tb[-1400:]
            raw_box = ""
            if err.get("raw_response"):
                raw_clean = str(err["raw_response"]).strip().replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")[:700]
                raw_box = f"📄 <i>پاسخ خام سرور / API:</i>\n<pre><code class=\"language-json\">{raw_clean}</code></pre>\n"
            error_section += (
                f"\n<b>{i+1}. {err['error_type']}</b> در <code>{err['endpoint']}</code> ({t_str}):\n"
                f"💬 <code>{err['error_msg']}</code>\n"
                f"{raw_box}"
                f"💻 <b>استک‌تریس و خطوط کد:</b>\n"
                f"<pre><code class=\"language-python\">{full_tb}</code></pre>\n"
            )
    else:
        error_section = "\n✅ <b>وضعیت سلامت ارورها:</b> تمامی سرویس‌ها کاملاً سبز و پایدار هستند (هیچ خطایی ثبت نشده است)."

    report = (
        f"🛡️ <b>گزارش جامع وضعیت سرور و سیستم (Owner VIP Diagnostic)</b> 📊\n\n"
        f"🕒 <b>زمان گزارش:</b> <code>{now_iran}</code>\n\n"
        f"🖥️ <b>منابع سخت‌افزاری سرور:</b>\n"
        f"▫️ مصرف پردازنده (CPU): <b>{cpu}%</b>\n"
        f"▫️ حافظه رم (RAM): <b>{mem_used} GB</b> از {mem_total} GB ({mem_pct}%)\n"
        f"▫️ فضای دیسک (Disk): <b>{disk_used} GB</b> از {disk_total} GB ({disk.percent}%)\n"
        f"▫️ اتصالات لایو وب‌سوکت: <b>{ws_conns} کلاینت آنلاین</b>\n\n"
        f"👥 <b>وضعیت دیتابیس و کاربران:</b>\n"
        f"▫️ کل کاربران: <b>{total_users} نفر</b> (فعال: {active_users})\n"
        f"▫️ تکالیف فعال کلاسی: <b>{total_assignments} تکلیف</b>\n\n"
        f"🤖 <b>تنظیمات هوش مصنوعی و ربات:</b>\n"
        f"▫️ یوزرنیم ربات: <b>@{bot_user}</b>\n"
        f"▫️ سرویس‌دهنده AI: <code>{provider}</code>\n"
        f"▫️ مدل فعال: <code>{model}</code>\n"
        f"{error_section}\n\n"
        f"📱 <i>گزارش به درخواست مدیریت ارشد صادر گردید.</i>"
    )
    return report
