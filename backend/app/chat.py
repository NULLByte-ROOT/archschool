from fastapi import HTTPException
from sqlalchemy.orm import Session

from . import models, schemas


def dm_room(user_a: int, user_b: int) -> str:
    low, high = sorted((user_a, user_b))
    return f"dm:{low}:{high}"


def room_from_message(
    user_id: int, receiver_id: int | None, assignment_id: int | None
) -> str:
    if receiver_id:
        return dm_room(user_id, receiver_id)
    if assignment_id:
        return f"assignment:{assignment_id}"
    return "global"


def resolve_room(db: Session, room: str, user_id: int) -> dict:
    """Validate a room and return the fields a message in it must have."""
    if room == "global":
        return {"receiver_id": None, "assignment_id": None}

    if room.startswith("dm:"):
        parts = room.split(":")
        if len(parts) != 3:
            raise HTTPException(status_code=400, detail="اتاق گفتگو نامعتبر است")
        try:
            first, second = int(parts[1]), int(parts[2])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="اتاق گفتگو نامعتبر است") from exc
        if user_id not in (first, second):
            raise HTTPException(status_code=403, detail="دسترسی به این گفتگو مجاز نیست")
        peer_id = second if first == user_id else first
        peer = (
            db.query(models.User)
            .filter(models.User.id == peer_id, models.User.is_active.is_(True))
            .first()
        )
        if not peer:
            raise HTTPException(status_code=404, detail="کاربر پیدا نشد")
        return {"receiver_id": peer_id, "assignment_id": None}

    if room.startswith("assignment:"):
        raw_id = room.split(":", 1)[1]
        try:
            assignment_id = int(raw_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="اتاق گفتگو نامعتبر است") from exc
        assignment = (
            db.query(models.Assignment)
            .filter(models.Assignment.id == assignment_id)
            .first()
        )
        if not assignment:
            raise HTTPException(status_code=404, detail="تکلیف پیدا نشد")
        return {"receiver_id": None, "assignment_id": assignment_id}

    raise HTTPException(status_code=400, detail="اتاق گفتگو نامعتبر است")


def validate_file_url(file_url: str | None) -> None:
    if file_url and not file_url.startswith("/api/media/"):
        raise HTTPException(status_code=400, detail="آدرس فایل نامعتبر است")


def message_payload(message: models.Message) -> dict:
    return schemas.MessageOut.model_validate(message).model_dump(mode="json")
