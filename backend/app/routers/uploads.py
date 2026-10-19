import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from .. import models, schemas
from ..dependencies import get_current_user
from ..storage import save_upload

logger = logging.getLogger("archschool.uploads")

router = APIRouter()


# `POST /api/uploads` (no trailing slash) is registered as an alias so a
# reverse proxy can never turn the upload into a 307 redirect, which some
# clients/proxies handle badly for multipart POST bodies.
@router.post("", response_model=schemas.UploadOut, include_in_schema=False)
@router.post("/", response_model=schemas.UploadOut)
async def upload_file(
    file: UploadFile = File(...),
    user: models.User = Depends(get_current_user),
):
    try:
        url, file_name, size = await save_upload(file)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Upload failed for user_id=%s name=%r", user.id, file.filename)
        raise HTTPException(status_code=500, detail="آپلود فایل ناموفق بود")

    logger.info(
        "Uploaded %r (%d bytes) by user_id=%s -> %s",
        file_name,
        size,
        user.id,
        url,
    )
    return schemas.UploadOut(url=url, file_name=file_name, size=size)
