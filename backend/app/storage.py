import re
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

from .config import settings

UPLOAD_DIR = Path(settings.UPLOAD_DIR)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_BYTES = settings.MAX_UPLOAD_MB * 1024 * 1024
_SAFE_SUFFIX = re.compile(r"^\.[a-z0-9]{1,10}$")
_CHUNK = 1024 * 1024


def media_url(stored_name: str) -> str:
    return f"/api/media/{stored_name}"


async def save_upload(file: UploadFile) -> tuple[str, str, int]:
    """Save an uploaded file with a random name and return (url, name, size)."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="نام فایل نامعتبر است")

    suffix = Path(file.filename).suffix.lower()
    if not _SAFE_SUFFIX.match(suffix):
        suffix = ""

    stored_name = f"{uuid.uuid4().hex}{suffix}"
    destination = UPLOAD_DIR / stored_name
    size = 0

    try:
        with destination.open("wb") as out:
            while chunk := await file.read(_CHUNK):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"حجم فایل نباید بیشتر از {settings.MAX_UPLOAD_MB} مگابایت باشد",
                    )
                out.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await file.close()

    if size == 0:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="فایل خالی است")

    return media_url(stored_name), file.filename, size
