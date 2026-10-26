"""Expo push transport.

The mobile client registers Expo push tokens (``ExponentPushToken[...]``); this
module delivers notifications through Expo's HTTP push service. Delivery must
never block a chat message or an assignment save: :func:`dispatch_push` boots
the request in a background task (or a daemon thread when called from a sync
FastAPI endpoint), and every failure is logged instead of raised.

Expo's API accepts at most 100 messages per request and answers HTTP 200 even
when individual tickets fail, so the response body is inspected for
``DeviceNotRegistered`` and those tokens are pruned from the database.

Diagnostics: :func:`send_push_report` sends once and returns Expo's raw
per-token tickets. It backs ``POST /api/users/push-token/test`` so a silent
"nothing arrives" can be narrowed down to *no token*, *bad FCM credentials*
(``InvalidCredentials`` / ``MismatchSenderId``) or *app uninstalled*
(``DeviceNotRegistered``) from a single request.

If the Expo project has "enhanced push security" enabled, requests must carry
``Authorization: Bearer <EXPO_ACCESS_TOKEN>``; set that env var and the header
is added automatically.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, Iterable

import httpx

from .config import settings

logger = logging.getLogger("archschool.push")

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
BATCH_SIZE = 100

# Keep a strong reference to in-flight tasks; asyncio only holds weak refs and a
# garbage-collected task would silently drop the notification.
_tasks: set[asyncio.Task[None]] = set()


def _clip(value: str, limit: int) -> str:
    value = (value or "").strip()
    return value if len(value) <= limit else f"{value[: limit - 1]}…"


def _headers() -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip, deflate",
        "Content-Type": "application/json",
    }
    access_token = (settings.EXPO_ACCESS_TOKEN or "").strip()
    if access_token:
        # Only required when the Expo project enables enhanced push security;
        # harmless otherwise (the public endpoint ignores it).
        headers["Authorization"] = f"Bearer {access_token}"
    return headers


def _messages(
    tokens: Iterable[str],
    title: str,
    body: str,
    data: dict[str, Any] | None,
    channel_id: str,
    sound: str | None,
) -> list[dict[str, Any]]:
    payload = []
    for token in tokens:
        message: dict[str, Any] = {
            "to": token,
            "title": _clip(title, 120),
            "body": _clip(body, 240),
            "data": data or {},
            "priority": "high",
        }
        if channel_id:
            # Android uses this to pick the notification channel created by the
            # app; iOS ignores unknown keys.
            message["channelId"] = channel_id
        if sound:
            message["sound"] = sound
        payload.append(message)
    return payload


def _ticket_entries(
    messages: list[dict[str, Any]], tickets: list[Any], http_status: int
) -> list[dict[str, Any]]:
    """Normalise Expo's ticket list into one dict per device."""
    entries: list[dict[str, Any]] = []
    for message, ticket in zip(messages, tickets):
        if not isinstance(ticket, dict):
            entries.append(
                {
                    "token": message["to"],
                    "status": "unknown",
                    "http_status": http_status,
                }
            )
            continue
        details = ticket.get("details") or {}
        entries.append(
            {
                "token": message["to"],
                "status": ticket.get("status") or "ok",
                "id": ticket.get("id"),
                "message": ticket.get("message"),
                "error": details.get("error") if isinstance(details, dict) else None,
                "http_status": http_status,
            }
        )
    return entries


def _short(token: str) -> str:
    return f"{str(token)[:18]}…"


def _prune_tokens(tokens: list[str]) -> None:
    """Delete tokens Expo reports as uninstalled/revoked."""
    if not tokens:
        return
    # Imported lazily so this module stays importable from anywhere.
    from .database import SessionLocal
    from . import models

    try:
        with SessionLocal() as db:
            deleted = (
                db.query(models.PushToken)
                .filter(models.PushToken.token.in_(tokens))
                .delete(synchronize_session=False)
            )
            db.commit()
        if deleted:
            logger.info("Pruned %d unregistered push token(s)", deleted)
    except Exception:  # pragma: no cover - pruning is best effort
        logger.warning("Could not prune unregistered push tokens", exc_info=True)


async def send_push(
    tokens: Iterable[str],
    title: str,
    body: str,
    data: dict[str, Any] | None = None,
    *,
    channel_id: str = "default",
    sound: str | None = "default",
) -> None:
    """Deliver one notification to every token, in Expo-sized batches."""
    if not settings.PUSH_NOTIFICATIONS_ENABLED:
        return

    unique = list(dict.fromkeys(token for token in tokens if token))
    if not unique:
        return

    headers = _headers()

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(20.0, connect=10.0)
    ) as client:
        for start in range(0, len(unique), BATCH_SIZE):
            chunk = unique[start : start + BATCH_SIZE]
            messages = _messages(chunk, title, body, data, channel_id, sound)
            try:
                response = await client.post(
                    EXPO_PUSH_URL, json=messages, headers=headers
                )
                if response.status_code >= 400:
                    logger.warning(
                        "Expo push rejected batch: HTTP %s %s",
                        response.status_code,
                        response.text[:300],
                    )
                    continue
                payload = response.json()
            except Exception:
                logger.exception("Expo push request failed (%d token(s))", len(chunk))
                continue

            tickets = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(tickets, list):
                logger.warning(
                    "Expo push returned an unexpected body: %s",
                    str(payload)[:300],
                )
                continue

            entries = _ticket_entries(messages, tickets, response.status_code)
            dead: list[str] = []
            failures = 0
            for entry in entries:
                if entry["status"] != "error":
                    continue
                failures += 1
                logger.info(
                    "Expo push ticket error token=%s error=%s message=%s",
                    _short(entry["token"]),
                    entry.get("error"),
                    entry.get("message"),
                )
                if entry.get("error") == "DeviceNotRegistered":
                    dead.append(entry["token"])
            logger.info(
                "Expo push batch done: ok=%d error=%d channel=%s title=%r",
                len(entries) - failures,
                failures,
                channel_id,
                title,
            )
            _prune_tokens(dead)


async def send_push_report(
    tokens: Iterable[str],
    title: str,
    body: str,
    data: dict[str, Any] | None = None,
    *,
    channel_id: str = "default",
    sound: str | None = "default",
) -> list[dict[str, Any]]:
    """Send once and return Expo's per-token tickets instead of swallowing them.

    Used by the owner-facing diagnostics endpoint. A returned ``401`` /
    ``InvalidCredentials`` means the FCM V1 service account is missing or wrong,
    while ``DeviceNotRegistered`` means the token belongs to an uninstalled app.
    """
    unique = [token for token in dict.fromkeys(tokens) if token]
    report: list[dict[str, Any]] = []
    if not unique:
        return report

    headers = _headers()

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(20.0, connect=10.0)
    ) as client:
        for start in range(0, len(unique), BATCH_SIZE):
            chunk = unique[start : start + BATCH_SIZE]
            messages = _messages(chunk, title, body, data, channel_id, sound)
            try:
                response = await client.post(
                    EXPO_PUSH_URL, json=messages, headers=headers
                )
            except Exception as exc:
                logger.exception("Expo push probe failed (%d token(s))", len(chunk))
                report.extend(
                    {
                        "token": message["to"],
                        "status": "transport_error",
                        "message": str(exc)[:300],
                        "http_status": None,
                    }
                    for message in messages
                )
                continue

            if response.status_code >= 400:
                logger.warning(
                    "Expo push probe rejected: HTTP %s %s",
                    response.status_code,
                    response.text[:300],
                )
                report.extend(
                    {
                        "token": message["to"],
                        "status": "http_error",
                        "message": response.text[:300],
                        "http_status": response.status_code,
                    }
                    for message in messages
                )
                continue

            try:
                payload = response.json()
            except Exception as exc:
                report.extend(
                    {
                        "token": message["to"],
                        "status": "bad_response",
                        "message": str(exc)[:300],
                        "http_status": response.status_code,
                    }
                    for message in messages
                )
                continue

            tickets = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(tickets, list):
                report.extend(
                    {
                        "token": message["to"],
                        "status": "bad_response",
                        "message": str(payload)[:300],
                        "http_status": response.status_code,
                    }
                    for message in messages
                )
                continue

            entries = _ticket_entries(messages, tickets, response.status_code)
            for entry in entries:
                logger.info(
                    "Expo push probe token=%s status=%s error=%s message=%s",
                    _short(entry["token"]),
                    entry.get("status"),
                    entry.get("error"),
                    entry.get("message"),
                )
            report.extend(entries)
            _prune_tokens(
                [
                    entry["token"]
                    for entry in entries
                    if entry.get("error") == "DeviceNotRegistered"
                ]
            )

    return report


def _run_async_in_thread(
    tokens: list[str],
    title: str,
    body: str,
    data: dict[str, Any] | None,
    channel_id: str,
    sound: str | None,
) -> None:
    try:
        asyncio.run(send_push(tokens, title, body, data, channel_id=channel_id, sound=sound))
    except Exception:  # pragma: no cover - never surface to the caller
        logger.exception("Background push worker crashed")


def dispatch_push(
    tokens: Iterable[str],
    title: str,
    body: str,
    data: dict[str, Any] | None = None,
    *,
    channel_id: str = "default",
    sound: str | None = "default",
) -> None:
    """Fire-and-forget delivery from sync or async code.

    Async callers (REST handlers, the WebSocket loop, the deadline watcher) get
    a task on the running loop. Sync endpoints run in Starlette's threadpool,
    where there is no loop, so a daemon thread owns the request instead.

    Every dispatch is logged at INFO: a chat message that produced
    ``push skipped — no tokens`` is a missing registration, not a delivery
    failure, and the distinction matters when debugging a silent phone.
    """
    unique = [token for token in dict.fromkeys(tokens) if token]

    if not settings.PUSH_NOTIFICATIONS_ENABLED:
        logger.info(
            "push disabled — dropped %d token(s) for %r", len(unique), title
        )
        return

    if not unique:
        logger.info("push skipped — no registered tokens for %r", title)
        return

    logger.info(
        "push dispatch tokens=%d channel=%s title=%r",
        len(unique),
        channel_id,
        title,
    )

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None:
        task = loop.create_task(
            send_push(unique, title, body, data, channel_id=channel_id, sound=sound)
        )
        _tasks.add(task)
        task.add_done_callback(_tasks.discard)
        return

    threading.Thread(
        target=_run_async_in_thread,
        args=(unique, title, body, data, channel_id, sound),
        name="archschool-push",
        daemon=True,
    ).start()
