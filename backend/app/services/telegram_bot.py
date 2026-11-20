import asyncio
from datetime import datetime, timedelta, timezone
import logging
import re
import secrets
from typing import Any, Dict, List, Optional
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

    # Route Google Gemini through host IPv6 gateway to bypass Contabo IPv4 blacklist
    if "generativelanguage.googleapis.com" in clean_base:
        clean_base = clean_base.replace(
            "https://generativelanguage.googleapis.com",
            "https://archschool.vidxsepehr.ir/gemini",
        )

    models_url = f"{clean_base}/models"
    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json",
    }
    if "openrouter.ai" in clean_base:
        headers["HTTP-Referer"] = "https://archschool.vidxsepehr.ir"
        headers["X-Title"] = "ArchSchool Assistant"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
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
    return {
        "bot_token": data.get("telegram_bot_token", ""),
        "group_id": data.get("telegram_group_id", ""),
        "ai_provider": provider,
        "ai_api_key": api_key,
        "ai_base_url": data.get("ai_base_url") or def_base,
        "ai_model": data.get("ai_model") or def_model,
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


async def send_telegram_message(
    token: str,
    chat_id: str | int,
    text: str,
    parse_mode: str = "HTML",
    reply_to_message_id: Optional[int] = None,
    reply_markup: Optional[Dict[str, Any]] = None,
) -> bool:
    """Send a message via Telegram Bot HTTP API with automatic HTML sanitization and fallback."""
    if not token or not chat_id:
        return False

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
                return True
            logger.warning("Telegram sendMessage error: %s %s", resp.status_code, resp.text)

            # Fallback: if Telegram rejected the HTML entities, send as clean plain text
            if parse_mode:
                plain_payload = dict(payload)
                plain_payload.pop("parse_mode", None)
                # Strip HTML tags for clean fallback
                plain_payload["text"] = re.sub(r'<[^>]+>', '', formatted_text)
                fallback_resp = await client.post(url, json=plain_payload)
                if fallback_resp.status_code == 200:
                    logger.info("Telegram message sent successfully using plain-text fallback")
                    return True
    except Exception as exc:
        logger.error("Failed to send Telegram message: %s", exc)
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
                return True
            logger.warning("Telegram editMessageText error: %s %s", resp.status_code, resp.text)
            if parse_mode:
                plain_payload = dict(payload)
                plain_payload.pop("parse_mode", None)
                plain_payload["text"] = re.sub(r'<[^>]+>', '', formatted_text)
                fallback_resp = await client.post(url, json=plain_payload)
                return fallback_resp.status_code == 200
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


async def broadcast_deadline_announcement(
    db: Session,
    assignment: models.Assignment,
    hours_left: float,
) -> bool:
    """Send approaching deadline warning to the Telegram group."""
    token = get_bot_setting(db, "telegram_bot_token")
    group_id = get_bot_setting(db, "telegram_group_id")
    enabled = get_bot_setting(db, "telegram_bot_enabled", "true").lower() in ("true", "1")

    if not token or not group_id or not enabled:
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

    text = (
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

    if not token or not group_id or not enabled:
        return False

    from . import school_knowledge
    subj_info = school_knowledge.resolve_subject(assignment.subject_id or assignment.course or "")
    teacher = f" (استاد {subj_info['teacher']})" if subj_info else ""
    subj_name = subj_info["name"] if subj_info else (assignment.subject_id or "عمومی")

    due_str = "بدون مهلت تحویل"
    if assignment.due_date:
        due_str = school_knowledge.format_iran_datetime(assignment.due_date)

    is_reminder = getattr(assignment, "is_reminder_only", False)
    header = "📌 <b>یادآوری جدید کلاس ثبت شد!</b>" if is_reminder else "📢 <b>تکلیف جدید در سامانه ثبت شد!</b> 📚🔥"

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
