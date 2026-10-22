from datetime import datetime, UTC

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..config import settings
from ..database import get_db
from ..dependencies import get_current_user
from ..security import (
    create_access_token,
    generate_code,
    is_valid_access_code,
    normalize_access_code,
    normalize_username,
)

router = APIRouter()


def _find_user(db: Session, username: str) -> models.User | None:
    """Case-insensitive lookup so `ali` and `Ali` resolve to the same account."""
    return (
        db.query(models.User)
        .filter(func.lower(models.User.username) == username.strip().lower())
        .first()
    )


def _touch(user: models.User) -> None:
    user.last_seen = datetime.now(UTC).replace(tzinfo=None)


@router.post("/register", response_model=schemas.LoginResponse, status_code=201)
def register(data: schemas.RegisterRequest, db: Session = Depends(get_db)):
    username = normalize_username(data.username)
    if len(username) < 2:
        raise HTTPException(status_code=400, detail="نام کاربری خیلی کوتاه است")

    code = normalize_access_code(data.code)
    if not is_valid_access_code(code):
        raise HTTPException(
            status_code=400,
            detail="کد دسترسی باید دقیقاً ۶ کاراکتر و فقط شامل اعداد و حروف انگلیسی بزرگ باشد",
        )
    if code == settings.ADMIN_CODE:
        raise HTTPException(status_code=400, detail="این کد دسترسی قابل استفاده نیست")
    if code == normalize_access_code(settings.OWNER_ACCESS_CODE or ""):
        raise HTTPException(status_code=400, detail="این کد دسترسی قابل استفاده نیست")

    if _find_user(db, username):
        raise HTTPException(status_code=400, detail="این نام کاربری قبلاً گرفته شده")

    code_taken = (
        db.query(models.User)
        .filter(func.upper(models.User.code) == code)
        .first()
    )
    if code_taken:
        raise HTTPException(status_code=400, detail="این کد دسترسی قبلاً استفاده شده است")

    user = models.User(
        username=username,
        code=code,
        password=None,
        avatar_url=None,
        bio="",
        is_admin=False,
        role=models.ROLE_MEMBER,
        is_active=True,
        last_seen=datetime.now(UTC).replace(tzinfo=None),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token({"sub": str(user.id), "is_admin": user.is_admin})
    return schemas.LoginResponse(access_token=token, user=user)


@router.post("/login", response_model=schemas.LoginResponse)
def login(data: schemas.LoginRequest, db: Session = Depends(get_db)):
    username = normalize_username(data.username)
    if not username:
        raise HTTPException(status_code=400, detail="نام کاربری الزامی است")

    code = normalize_access_code(data.code)
    if not is_valid_access_code(code):
        raise HTTPException(
            status_code=400,
            detail="کد دسترسی باید دقیقاً ۶ کاراکتر و فقط شامل اعداد و حروف انگلیسی بزرگ باشد",
        )

    if code == settings.ADMIN_CODE:
        user = _find_user(db, username)
        if not user:
            user = models.User(
                username=username,
                code=generate_code(),
                is_admin=True,
                role=models.ROLE_ADMIN,
                is_active=True,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        elif not user.is_admin:
            raise HTTPException(status_code=403, detail="Username taken")
    elif code == normalize_access_code(settings.OWNER_ACCESS_CODE or ""):
        owner = _find_user(db, username)
        if not owner:
            raise HTTPException(status_code=401, detail="نام کاربری یا کد اشتباه است")
        if not owner.is_active:
            raise HTTPException(status_code=403, detail="حساب غیرفعال است")
        if not models.is_owner(owner):
            raise HTTPException(status_code=403, detail="Username taken")
        user = owner
    else:
        user = (
            db.query(models.User)
            .filter(
                func.lower(models.User.username) == username.lower(),
                func.upper(models.User.code) == code,
            )
            .first()
        )
        if not user:
            raise HTTPException(status_code=401, detail="نام کاربری یا کد اشتباه است")
        if not user.is_active:
            raise HTTPException(status_code=403, detail="حساب غیرفعال است")

    _touch(user)
    db.commit()
    db.refresh(user)

    token = create_access_token({"sub": str(user.id), "is_admin": user.is_admin})
    return schemas.LoginResponse(access_token=token, user=user)


@router.get("/me", response_model=schemas.UserOut)
def me(
    current: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the fresh user record so role changes apply without re-login."""
    _touch(current)
    db.commit()
    db.refresh(current)
    return current
