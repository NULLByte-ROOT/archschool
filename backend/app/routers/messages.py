from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from .. import chat, models, schemas
from ..database import get_db
from ..dependencies import get_current_user
from ..ws_manager import manager

router = APIRouter()


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

    message = models.Message(
        sender_id=current.id,
        receiver_id=room_fields["receiver_id"],
        assignment_id=room_fields["assignment_id"],
        content=content,
        file_url=data.file_url,
    )
    db.add(message)
    db.commit()
    db.refresh(message)

    await manager.broadcast_message(room, chat.message_payload(message))
    return message
