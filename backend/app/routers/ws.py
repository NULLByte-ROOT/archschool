import json
import logging
from datetime import datetime, UTC

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from .. import chat, models
from ..database import SessionLocal
from ..security import decode_token
from ..ws_manager import manager

router = APIRouter()
logger = logging.getLogger("archschool.ws")


def _authenticate(token: str | None) -> models.User | None:
    if not token:
        return None
    payload = decode_token(token)
    if not payload or not payload.get("sub"):
        return None
    # A malformed `sub` must be a clean 403 handshake rejection, never a 500:
    # a 500 leaves the browser with an opaque failed handshake and the client
    # retrying a token that can never work.
    try:
        user_id = int(payload["sub"])
    except (TypeError, ValueError):
        return None
    with SessionLocal() as db:
        user = (
            db.query(models.User)
            .filter(models.User.id == user_id)
            .first()
        )
        if not user or not user.is_active:
            return None
        user.last_seen = datetime.now(UTC).replace(tzinfo=None)
        db.commit()
        db.expunge(user)
        return user


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
    await websocket.accept()

    user = _authenticate(token)
    if not user:
        logger.warning("ws rejected: invalid or expired token (room=%s)", room)
        await websocket.close(code=1008, reason="invalid-token")
        return

    with SessionLocal() as db:
        try:
            room_fields = chat.resolve_room(db, room, user.id)
        except HTTPException as exc:
            logger.warning(
                "ws rejected: user=%s room=%s (%s)", user.id, room, exc.detail
            )
            await websocket.close(code=1008, reason="invalid-room")
            return

    await manager.connect(websocket, room, accept=False)
    logger.info("ws open: user=%s room=%s", user.id, room)

    try:
        while True:
            raw = await websocket.receive_text()

            if raw == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await manager.send_error(websocket, "پیام نامعتبر است")
                continue

            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
                continue

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
                continue

            if not content and not file_url:
                await manager.send_error(websocket, "پیام خالی است")
                continue

            if room == "global" and (
                data.get("receiver_id") or data.get("assignment_id")
            ):
                await manager.send_error(websocket, "اتاق پیام نامعتبر است")
                continue
            if room.startswith("dm:"):
                requested_peer = data.get("receiver_id")
                if requested_peer is not None and requested_peer != room_fields["receiver_id"]:
                    await manager.send_error(websocket, "گیرنده پیام نامعتبر است")
                    continue
            if room.startswith("assignment:"):
                requested_assignment = data.get("assignment_id")
                if (
                    requested_assignment is not None
                    and requested_assignment != room_fields["assignment_id"]
                ):
                    await manager.send_error(websocket, "تکلیف پیام نامعتبر است")
                    continue

            with SessionLocal() as db:
                try:
                    resolved_reply = chat.validate_reply(
                        db,
                        reply_to_id,
                        user.id,
                        room_fields["receiver_id"],
                        room_fields["assignment_id"],
                    )
                except HTTPException as exc:
                    await manager.send_error(websocket, exc.detail)
                    continue

                message = models.Message(
                    sender_id=user.id,
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

            await manager.broadcast_message(room, payload)

    except WebSocketDisconnect:
        logger.info("ws disconnect: user=%s room=%s", user.id, room)
    except Exception:
        logger.exception("ws error: user=%s room=%s", user.id, room)
        raise
    finally:
        manager.disconnect(websocket, room)
