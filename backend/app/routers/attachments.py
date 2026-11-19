import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..dependencies import get_current_user
from ..storage import UPLOAD_DIR, _SAFE_STORED_NAME, delete_upload

logger = logging.getLogger("archschool.attachments")

router = APIRouter()


@router.get("/{attachment_id}/download")
def download_attachment(
    attachment_id: int,
    db: Session = Depends(get_db),
):
    """Serve attachment file for browser or device download manager."""
    attachment = (
        db.query(models.Attachment)
        .filter(models.Attachment.id == attachment_id)
        .first()
    )
    if not attachment:
        raise HTTPException(status_code=404, detail="پیوست پیدا نشد")

    name = attachment.file_url.rsplit("/", 1)[-1].split("?", 1)[0]
    if not _SAFE_STORED_NAME.match(name):
        raise HTTPException(status_code=400, detail="نام فایل نامعتبر است")

    file_path = UPLOAD_DIR / name
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="فایل روی سرور یافت نشد")

    safe_filename = attachment.file_name or name
    return FileResponse(
        path=file_path,
        filename=safe_filename,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{safe_filename}"'},
    )


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
