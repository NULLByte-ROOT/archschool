import json
import logging
from datetime import datetime, UTC

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from .. import chat, models, notifications
from ..database import SessionLocal
from ..security import decode_token
from ..ws_manager import manager

router = APIRouter()
logger = logging.getLogger("archschool.ws")


def _authenticate(token: str | None) -> tuple[int, bool] | None:
    """Return (user id, role) for the token owner, or None.

    Returns the *id*, never the ORM instance. `db.commit()` expires every
    attribute of the instance (``expire_on_commit`` defaults to True) and
    ``db.expunge()`` then detaches it, so the very first attribute access after
    returning — ``user.id`` — raises ``DetachedInstanceError: Instance <User> is
    not bound to a Session``. That crash happened *after* ``accept()``, so
    uvicorn dropped the TCP connection and the browser could only report 1006,
    over and over, forever. Reading the id while the instance is still attached
    removes the whole class of bug.
    """
    if not token:
        return None
    payload = decode_token(token)
    if not payload or not payload.get("sub"):
        return None
    # A malformed `sub` must be a clean 1008 close, never a 500: a 500 leaves
    # the browser with an opaque drop and the client retrying a token that can
    # never work.
    try:
        user_id = int(payload["sub"])
    except (TypeError, ValueError):
        return None

    with SessionLocal() as db:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user or not user.is_active:
            return None
        uid = user.id  # read while the instance is still attached
        role = user.role  # members are read-only even on the socket
        try:
            user.last_seen = datetime.now(UTC).replace(tzinfo=None)
            db.commit()
        except Exception:
            # Losing the presence update is harmless; losing the socket is not.
            db.rollback()
            logger.warning(
                "ws auth: could not update last_seen user=%s", uid, exc_info=True
            )
        return uid, role


async def _safe_close(websocket: WebSocket, code: int, reason: str) -> None:
    """Close without ever masking the real error with a second exception."""
    try:
        if websocket.client_state is not WebSocketState.DISCONNECTED:
            await websocket.close(code=code, reason=reason)
    except Exception:
        logger.debug("ws close failed (peer already gone)", exc_info=True)


async def _handle_frame(
    websocket: WebSocket,
    room: str,
    user_id: int,
    room_fields: dict,
    role: str,
    raw: str,
) -> None:
    """Process one client frame. Callers isolate exceptions per frame."""
    if raw == "ping":
        await websocket.send_json({"type": "pong"})
        return

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        await manager.send_error(websocket, "پیام نامعتبر است")
        return

    if not isinstance(data, dict):
        await manager.send_error(websocket, "پیام نامعتبر است")
        return

    if data.get("type") == "ping":
        await websocket.send_json({"type": "pong"})
        return

    if room == "pulse":
        # The pulse channel is read-only: it only receives unread pings and
        # keeps the session warm with pings. Nothing else is accepted.
        await manager.send_error(websocket, "این اتصال فقط برای اعلان است")
        return

    is_member = role == models.ROLE_MEMBER
    if is_member and not room.startswith("assignment:"):
        # Members may only speak inside assignment comment rooms; any other
        # room stays read-only for them and never reaches broadcast.
        await manager.send_error(
            websocket, "برای دسترسی به گفتگو، از ادمین اجازه بگیرید."
        )
        return

    content = str(data.get("content") or "").strip()[:5000]
    file_url = data.get("file_url")
    if file_url is not None and not isinstance(file_url, str):
        file_url = None

    reply_to_id = data.get("reply_to_id")
    if isinstance(reply_to_id, str) and reply_to_id.isdigit():
        reply_to_id = int(reply_to_id)
    if not isinstance(reply_to_id, int):
        reply_to_id = None

    try:
        chat.validate_file_url(file_url)
    except HTTPException as exc:
        await manager.send_error(websocket, exc.detail)
        return

    if not content and not file_url:
        await manager.send_error(websocket, "پیام خالی است")
        return

    if room == "global" and (data.get("receiver_id") or data.get("assignment_id")):
        await manager.send_error(websocket, "اتاق پیام نامعتبر است")
        return
    if room.startswith("dm:"):
        requested_peer = data.get("receiver_id")
        if requested_peer is not None and requested_peer != room_fields["receiver_id"]:
            await manager.send_error(websocket, "گیرنده پیام نامعتبر است")
            return
    if room.startswith("assignment:"):
        requested_assignment = data.get("assignment_id")
        if (
            requested_assignment is not None
            and requested_assignment != room_fields["assignment_id"]
        ):
            await manager.send_error(websocket, "تکلیف پیام نامعتبر است")
            return

    with SessionLocal() as db:
        try:
            resolved_reply = chat.validate_reply(
                db,
                reply_to_id,
                user_id,
                room_fields["receiver_id"],
                room_fields["assignment_id"],
            )
        except HTTPException as exc:
            await manager.send_error(websocket, exc.detail)
            return

        message = models.Message(
            sender_id=user_id,
            receiver_id=room_fields["receiver_id"],
            assignment_id=room_fields["assignment_id"],
            content=content,
            file_url=file_url,
            reply_to_id=resolved_reply,
        )
        db.add(message)
        db.commit()
        db.refresh(message)
        payload = chat.message_payload(message)

        # Inside the session: the push audience queries need a live DB handle,
        # and the payload already carries the sender/room metadata.
        notifications.notify_chat_message(
            db,
            sender_id=user_id,
            sender_username=payload.get("sender_username"),
            receiver_id=payload.get("receiver_id"),
            assignment_id=payload.get("assignment_id"),
            content=payload.get("content") or "",
            has_file=bool(payload.get("file_url")),
            message_id=int(payload["id"]),
            assignment_title=payload.get("assignment_title"),
        )

    await manager.broadcast_message(room, payload)
    await manager.notify_message_pulses(payload)


@router.websocket("/api/ws")
async def chat_socket(websocket: WebSocket):
    token = websocket.query_params.get("token")
    room = websocket.query_params.get("room", "global")

    # First line on purpose: proves the upgrade actually reached FastAPI and
    # shows what the proxies in front of us forwarded. The token itself is
    # never logged.
    logger.info(
        "ws handshake room=%s token=%s host=%s origin=%s xff=%s",
        room,
        "present" if token else "MISSING",
        websocket.headers.get("host", "-"),
        websocket.headers.get("origin", "-"),
        websocket.headers.get("x-forwarded-for", "-"),
    )

    # Accept *before* validating. A close before the handshake completes is a
    # failed HTTP response: the browser can only report it as 1006 (abnormal
    # closure) and the app never learns why. Accepting first lets us close with
    # 1008 + a reason the client can read and act on.
    try:
        await websocket.accept()
    except Exception:
        logger.exception("ws accept failed: room=%s", room)
        return

    user_id: int | None = None
    role: str | None = None
    connected = False
    try:
        auth = _authenticate(token)
        if auth is None:
            logger.warning("ws rejected: invalid or expired token (room=%s)", room)
            await _safe_close(websocket, 1008, "invalid-token")
            return
        user_id, role = auth

        try:
            if room == "pulse":
                # Notifications-only channel: no room membership required.
                # It exists so unread counts can reach the user anywhere in
                # the app, not just inside the chat page.
                room_fields = {}
            else:
                with SessionLocal() as db:
                    room_fields = chat.resolve_room(db, room, user_id)
        except HTTPException as exc:
            logger.warning(
                "ws rejected: user=%s room=%s (%s)", user_id, room, exc.detail
            )
            await _safe_close(websocket, 1008, "invalid-room")
            return

        await manager.connect(
            websocket, room, accept=False, user_id=user_id
        )
        connected = True
        logger.info("ws open: user=%s room=%s", user_id, room)

        while True:
            try:
                raw = await websocket.receive_text()
            except WebSocketDisconnect:
                logger.info("ws disconnect: user=%s room=%s", user_id, room)
                break
            except Exception:
                logger.exception(
                    "ws receive failed: user=%s room=%s", user_id, room
                )
                break

            # One broken frame (bad SQL, bad payload, unexpected None) must not
            # take the whole socket down: the client would see 1006 and redial
            # in a loop. Log it, tell the sender, keep the connection.
            try:
                await _handle_frame(
                    websocket, room, user_id, room_fields, role or "member", raw
                )
            except Exception:
                logger.exception(
                    "ws frame failed: user=%s room=%s", user_id, room
                )
                await manager.send_error(websocket, "خطا در پردازش پیام")

    except Exception:
        # Anything unhandled used to escape the endpoint, so uvicorn tore down
        # the TCP connection with no close frame (browser: 1006). Log the full
        # traceback and close with a real 1011 so the reason survives the proxies.
        logger.exception("ws crashed: user=%s room=%s", user_id, room)
        if connected:
            await _safe_close(websocket, 1011, "internal-error")
    finally:
        if connected:
            manager.disconnect(websocket, room)
            logger.info("ws closed: user=%s room=%s", user_id, room)
