import mimetypes
import re
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

from .config import settings

UPLOAD_DIR = Path(settings.UPLOAD_DIR)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_BYTES = settings.MAX_UPLOAD_MB * 1024 * 1024
_SAFE_SUFFIX = re.compile(r"^\.[a-z0-9]{1,10}$")
# stored files are `<32 hex uuid><optional suffix>`
_SAFE_STORED_NAME = re.compile(r"^[a-f0-9]{32}(?:\.[a-z0-9]{1,10})?$")
_CHUNK = 1024 * 1024

# Browsers sometimes send an empty/odd filename extension (mobile pickers,
# clipboard/drag-drop, etc.). When the extension is missing or unsafe we derive
# it from the declared MIME type so images/videos still get a recognizable
# suffix (and therefore the right Content-Type when served).
_EXT_BY_MIME = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/pjpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/avif": ".avif",
    "image/bmp": ".bmp",
    "image/x-ms-bmp": ".bmp",
    "image/svg+xml": ".svg",
    "image/tiff": ".tiff",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/quicktime": ".mov",
    "video/x-msvideo": ".avi",
    "application/pdf": ".pdf",
}

# Guarantee correct MIME detection even in slim containers whose
# /etc/mime.types may be missing (Starlette falls back to
# application/octet-stream otherwise, which breaks inline image previews).
for _ext, _mime in _EXT_BY_MIME.items():
    mimetypes.add_type(_mime, _ext)


def media_url(stored_name: str) -> str:
    return f"/api/media/{stored_name}"


def _resolve_suffix(file: UploadFile) -> str:
    suffix = Path(file.filename or "").suffix.lower()
    if _SAFE_SUFFIX.match(suffix):
        return suffix
    return _EXT_BY_MIME.get((file.content_type or "").lower(), "")


async def save_upload(file: UploadFile) -> tuple[str, str, int]:
    """Save an uploaded file with a random name and return (url, name, size)."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="نام فایل نامعتبر است")

    suffix = _resolve_suffix(file)
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


def delete_upload(file_url: str | None) -> bool:
    """Delete a stored upload given its public URL.

    Returns True when a file was removed. Refuses anything that is not a
    generated `<uuid>[.ext]` name inside UPLOAD_DIR (path-traversal guard).
    """
    if not file_url:
        return False

    name = file_url.rsplit("/", 1)[-1].split("?", 1)[0]
    if not _SAFE_STORED_NAME.match(name):
        return False

    base = UPLOAD_DIR.resolve()
    target = (base / name).resolve()
    if target.parent != base:
        return False

    try:
        target.unlink()
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return False
