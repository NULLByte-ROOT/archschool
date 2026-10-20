from datetime import datetime, timedelta, UTC
import re
import secrets
import jwt

from .config import settings

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 6
ACCESS_CODE_PATTERN = re.compile(r"^[A-Z0-9]{6}$")


def generate_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def normalize_access_code(code: str | None) -> str:
    return (code or "").strip().upper()


def is_valid_access_code(code: str) -> bool:
    return bool(ACCESS_CODE_PATTERN.fullmatch(code))


def normalize_username(username: str) -> str:
    """Trim whitespace and capitalise only the first character."""
    cleaned = (username or "").strip()
    if not cleaned:
        return ""
    return cleaned[0].upper() + cleaned[1:]


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except jwt.PyJWTError:
        return None