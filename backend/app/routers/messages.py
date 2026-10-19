from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from .. import chat, models, schemas
from ..database import get_db
from ..dependencies import get_current_user
from ..ws_manager import manager

router = APIRouter()


def _room_filter(message: models.Message):
    if message.assignment_id is not None:
        return models.Message.assignment_id == message.assignment_id
    if message.receiver_id is not None:
        return or_(
            and_(
                models.Message.sender_id == message.sender_id,
                models.Message.receiver_id == message.receiver_id,
            ),
            and_(
                models.Message.sender_id == message.receiver_id,
                models.Message.receiver_id == message.sender_id,
            ),
        )
    return and_(
        models.Message.receiver_id.is_(None),
        models.Message.assignment_id.is_(None),
    )


@router.get("/overview", response_model=schemas.ChatOverview)
def chat_overview(
    db: Session = Depends(get_db),
    current: models.User = Depends(get_current_user),
):
    latest_global = (
        db.query(models.Message)
        .filter(
            models.Message.receiver_id.is_(None),
            models.Message.assignment_id.is_(None),
        )
        .order_by(models.Message.created_at.desc(), models.Message.id.desc())
        .first()
    )

    rows = (
        db.query(models.Message)
        .filter(
            models.Message.receiver_id.isnot(None),
            or_(
                models.Message.sender_id == current.id,
                models.Message.receiver_id == current.id,
            ),
        )
        .order_by(models.Message.created_at.desc(), models.Message.id.desc())
        .limit(500)
        .all()
    )

    seen: set[int] = set()
    directs: list[schemas.DirectPreview] = []
    for message in rows:
        peer_id = (
            message.receiver_id
            if message.sender_id == current.id
            else message.sender_id
        )
        if not peer_id or peer_id in seen:
            continue
        seen.add(peer_id)
        directs.append(
            schemas.DirectPreview(
                peer_id=peer_id,
                message=schemas.MessageOut.model_validate(message),
            )
        )

    return schemas.ChatOverview(
        global_message=(
            schemas.MessageOut.model_validate(latest_global)
            if latest_global
            else None
        ),
        directs=directs,
    )


@router.get("/", response_model=list[schemas.MessageOut])
def list_messages(
    scope: Literal["global", "private", "assignment"] = Query("global"),
    peer_id: int | None = Query(None),
    assignment_id: int | None = Query(None),
    limit: int = Query(100, ge=1, le=300),
    db: Session = Depends(get_db),
    current: models.User = Depends(get_current_user),
):
    query = db.query(models.Message)

    if scope == "global":
        query = query.filter(
            models.Message.receiver_id.is_(None),
            models.Message.assignment_id.is_(None),
        )
    elif scope == "private":
        if not peer_id:
            raise HTTPException(status_code=400, detail="کاربر مقصد مشخص نیست")
        peer = (
            db.query(models.User)
            .filter(models.User.id == peer_id, models.User.is_active.is_(True))
            .first()
        )
        if not peer:
            raise HTTPException(status_code=404, detail="کاربر پیدا نشد")
        query = query.filter(
            or_(
                and_(
                    models.Message.sender_id == current.id,
                    models.Message.receiver_id == peer_id,
                ),
                and_(
                    models.Message.sender_id == peer_id,
                    models.Message.receiver_id == current.id,
                ),
            )
        )
    else:
        if not assignment_id:
            raise HTTPException(status_code=400, detail="تکلیف مشخص نیست")
        query = query.filter(models.Message.assignment_id == assignment_id)

    rows = (
        query.order_by(models.Message.created_at.desc(), models.Message.id.desc())
        .limit(limit)
        .all()
    )
    rows.reverse()
    return rows


@router.post("/", response_model=schemas.MessageOut, status_code=201)
async def create_message(
    data: schemas.MessageCreate,
    db: Session = Depends(get_db),
    current: models.User = Depends(get_current_user),
):
    content = data.content.strip()
    chat.validate_file_url(data.file_url)

    if not content and not data.file_url:
        raise HTTPException(status_code=400, detail="پیام خالی است")
    if data.receiver_id and data.assignment_id:
        raise HTTPException(
            status_code=400, detail="پیام نمی‌تواند هم‌زمان خصوصی و تکلیفی باشد"
        )
    if data.receiver_id == current.id:
        raise HTTPException(status_code=400, detail="به خودت نمی‌تونی پیام بدی")

    room = chat.room_from_message(current.id, data.receiver_id, data.assignment_id)
    room_fields = chat.resolve_room(db, room, current.id)

    reply_to_id = chat.validate_reply(
        db,
        data.reply_to_id,
        current.id,
        room_fields["receiver_id"],
        room_fields["assignment_id"],
    )

    message = models.Message(
        sender_id=current.id,
        receiver_id=room_fields["receiver_id"],
        assignment_id=room_fields["assignment_id"],
        content=content,
        file_url=data.file_url,
        reply_to_id=reply_to_id,
    )
    db.add(message)
    db.commit()
    db.refresh(message)

    await manager.broadcast_message(room, chat.message_payload(message))
    return message


@router.delete("/{message_id}", status_code=204)
async def delete_message(
    message_id: int,
    db: Session = Depends(get_db),
    current: models.User = Depends(get_current_user),
):
    message = chat.load_visible_message(db, message_id, current.id)
    if message.sender_id != current.id and not current.is_admin:
        raise HTTPException(
            status_code=403, detail="فقط فرستنده می‌تواند پیام را حذف کند"
        )
    room = chat.message_room(message)
    db.delete(message)
    db.commit()
    await manager.broadcast(room, {"type": "delete", "data": {"id": message_id}})
    return None


@router.post("/{message_id}/pin", response_model=schemas.MessageOut)
async def pin_message(
    message_id: int,
    db: Session = Depends(get_db),
    current: models.User = Depends(get_current_user),
):
    message = chat.load_visible_message(db, message_id, current.id)
    room = chat.message_room(message)
    db.query(models.Message).filter(_room_filter(message)).update(
        {"is_pinned": False}, synchronize_session=False
    )
    message.is_pinned = True
    db.commit()
    db.refresh(message)
    payload = chat.message_payload(message)
    await manager.broadcast(room, {"type": "pin", "data": payload})
    return message


@router.delete("/{message_id}/pin", response_model=schemas.MessageOut)
async def unpin_message(
    message_id: int,
    db: Session = Depends(get_db),
    current: models.User = Depends(get_current_user),
):
    message = chat.load_visible_message(db, message_id, current.id)
    room = chat.message_room(message)
    message.is_pinned = False
    db.commit()
    db.refresh(message)
    payload = chat.message_payload(message)
    await manager.broadcast(room, {"type": "pin", "data": payload})
    return message
