import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from ..database import get_db
from ..dependencies import get_current_user
from ..storage import delete_upload

logger = logging.getLogger("archschool.attachments")

router = APIRouter()


@router.delete("/{attachment_id}", status_code=204)
def delete_attachment(
    attachment_id: int,
    db: Session = Depends(get_db),
    current: models.User = Depends(get_current_user),
):
    attachment = (
        db.query(models.Attachment)
        .filter(models.Attachment.id == attachment_id)
        .first()
    )
    if not attachment:
        raise HTTPException(status_code=404, detail="پیوست پیدا نشد")

    is_owner = attachment.user_id == current.id
    if not is_owner and not current.is_admin:
        raise HTTPException(
            status_code=403, detail="فقط آپلودکننده یا مدیر می‌تواند فایل را حذف کند"
        )

    file_url = attachment.file_url

    # Only claw back the upload points when the uploader deletes their own file
    # (never when an admin removes someone else's), and never below zero.
    if (
        is_owner
        and settings.DEDUCT_POINTS_ON_ATTACHMENT_DELETE
        and current.points
    ):
        current.points = max(0, current.points - settings.POINTS_PER_UPLOAD)

    db.delete(attachment)
    db.commit()

    removed = delete_upload(file_url)
    logger.info(
        "Attachment %s deleted by user_id=%s (file removed=%s)",
        attachment_id,
        current.id,
        removed,
    )
    return None
