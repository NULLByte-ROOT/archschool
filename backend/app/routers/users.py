from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import List

from .. import chat, models, schemas
from ..database import get_db
from ..dependencies import get_current_admin, get_current_user
from ..security import (
    generate_code,
    is_valid_access_code,
    normalize_access_code,
    normalize_username,
)
from ..storage import delete_upload

router = APIRouter()


@router.get("/leaderboard", response_model=List[schemas.PublicUserOut])
def leaderboard(
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    return (
        db.query(models.User)
        .filter(models.User.is_active.is_(True))
        .order_by(models.User.points.desc(), models.User.username.asc())
        .all()
    )


@router.get("/team", response_model=List[schemas.PublicUserOut])
def team(
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    return (
        db.query(models.User)
        .filter(models.User.is_active.is_(True))
        .order_by(models.User.username.asc())
        .all()
    )


@router.patch("/me", response_model=schemas.UserOut)
def update_me(
    data: schemas.UserSelfUpdate,
    db: Session = Depends(get_db),
    current: models.User = Depends(get_current_user),
):
    updates = data.model_dump(exclude_unset=True)
    if "avatar_url" in updates:
        chat.validate_file_url(updates["avatar_url"])
    if "bio" in updates:
        updates["bio"] = (updates["bio"] or "").strip()
    for key, value in updates.items():
        setattr(current, key, value)
    db.commit()
    db.refresh(current)
    return current


@router.delete("/me/avatar", response_model=schemas.UserOut)
def delete_my_avatar(
    db: Session = Depends(get_db),
    current: models.User = Depends(get_current_user),
):
    previous = current.avatar_url
    current.avatar_url = None
    db.commit()
    db.refresh(current)
    if previous:
        delete_upload(previous)
    return current


@router.get("/{user_id}/profile", response_model=schemas.UserProfileOut)
def user_profile(
    user_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    user = (
        db.query(models.User)
        .filter(models.User.id == user_id, models.User.is_active.is_(True))
        .first()
    )
    if not user:
        raise HTTPException(status_code=404, detail="کاربر پیدا نشد")
    return user


@router.get("/", response_model=List[schemas.UserOut])
def list_users(
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_admin),
):
    return db.query(models.User).order_by(models.User.created_at.desc()).all()


@router.post("/", response_model=schemas.UserOut, status_code=201)
def create_user(
    data: schemas.UserCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin),
):
    username = normalize_username(data.username)
    exists = (
        db.query(models.User)
        .filter(func.lower(models.User.username) == username.lower())
        .first()
    )
    if exists:
        raise HTTPException(status_code=400, detail="این نام کاربری قبلاً گرفته شده")

    code = normalize_access_code(data.code) if data.code else generate_code()
    if not is_valid_access_code(code):
        raise HTTPException(
            status_code=400,
            detail="کد دسترسی باید دقیقاً ۶ کاراکتر و فقط شامل اعداد و حروف انگلیسی بزرگ باشد",
        )
    code_taken = (
        db.query(models.User)
        .filter(func.upper(models.User.code) == code)
        .first()
    )
    if code_taken:
        raise HTTPException(status_code=400, detail="این کد دسترسی قبلاً استفاده شده است")

    role = data.role or (models.ROLE_ADMIN if data.is_admin else models.ROLE_MEMBER)
    if role not in models.VALID_ROLES:
        raise HTTPException(status_code=400, detail="نقش نامعتبر است")

    # Only an owner may mint another owner; admins manage member/friend/admin.
    if role == models.ROLE_OWNER and not models.is_owner(current_user):
        raise HTTPException(
            status_code=403, detail="فقط Owner می‌تواند نقش Owner بسازد"
        )

    user = models.User(
        username=username,
        code=code,
        is_admin=role in (models.ROLE_ADMIN, models.ROLE_OWNER),
        role=role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=schemas.UserOut)
def update_user(
    user_id: int,
    data: schemas.UserUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    updates = data.model_dump(exclude_unset=True)

    # Role guardrails: admins manage member/admin; the owner role can only be
    # granted or revoked by an owner. An admin can also never touch the owner
    # account itself (demote/deactivate is owner business).
    if "role" in updates and updates["role"] not in models.VALID_ROLES:
        raise HTTPException(status_code=400, detail="نقش نامعتبر است")
    if models.is_owner(user) and not models.is_owner(current_user):
        if "role" in updates and updates["role"] != models.ROLE_OWNER:
            raise HTTPException(
                status_code=403, detail="فقط Owner می‌تواند حساب Owner را تغییر دهد"
            )
    if "role" in updates and updates["role"] == models.ROLE_OWNER:
        if not models.is_owner(current_user):
            raise HTTPException(
                status_code=403, detail="فقط Owner می‌تواند نقش Owner بسازد"
            )
    if updates.get("username"):
        updates["username"] = normalize_username(updates["username"])
    if "code" in updates and updates["code"] is not None:
        # کد دسترسی فقط از مسیر Owner قابل تغییر است
        if not models.is_owner(current_user):
            raise HTTPException(
                status_code=403,
                detail="فقط Owner می‌تواند کد دسترسی را تغییر دهد",
            )
        updates["code"] = normalize_access_code(updates["code"])
        if not is_valid_access_code(updates["code"]):
            raise HTTPException(
                status_code=400,
                detail="کد دسترسی باید دقیقاً ۶ کاراکتر و فقط شامل اعداد و حروف انگلیسی بزرگ باشد",
            )
        code_taken = (
            db.query(models.User)
            .filter(
                func.upper(models.User.code) == updates["code"],
                models.User.id != user.id,
            )
            .first()
        )
        if code_taken:
            raise HTTPException(
                status_code=400, detail="این کد دسترسی قبلاً استفاده شده است"
            )
    else:
        updates.pop("code", None)

    for key, value in updates.items():
        setattr(user, key, value)

    # Keep the legacy `is_admin` flag and the RBAC `role` in sync so both the
    # old admin-only checks and the new role checks agree. Owner keeps its
    # role even if only `is_admin` is patched.
    if "role" in updates:
        user.is_admin = user.role in (models.ROLE_ADMIN, models.ROLE_OWNER)
    elif "is_admin" in updates and not models.is_owner(user):
        user.role = models.ROLE_ADMIN if user.is_admin else models.ROLE_MEMBER

    db.commit()
    db.refresh(user)
    return user


@router.patch("/{user_id}/code", response_model=schemas.UserOut)
def change_user_code(
    user_id: int,
    data: schemas.UserCodeUpdate,
    db: Session = Depends(get_db),
    current: models.User = Depends(get_current_owner),
):
    """Change any user's 6-character access code. Owner-only by design."""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    code = normalize_access_code(data.code)
    if not is_valid_access_code(code):
        raise HTTPException(
            status_code=400,
            detail="کد دسترسی باید دقیقاً ۶ کاراکتر و فقط شامل اعداد و حروف انگلیسی بزرگ باشد",
        )
    code_taken = (
        db.query(models.User)
        .filter(func.upper(models.User.code) == code, models.User.id != user.id)
        .first()
    )
    if code_taken:
        raise HTTPException(status_code=400, detail="این کد دسترسی قبلاً استفاده شده است")

    # Respect the environment: the .env is the source of truth for the Owner's
    # own account and a later boot re-applies that value.
    if models.is_owner(user):
        owner_env_code = ""
        try:
            from ..config import settings

            owner_env_code = normalize_access_code(settings.OWNER_ACCESS_CODE or "")
        except Exception:  # pragma: no cover - normalize never raises
            owner_env_code = ""
        if models.is_owner(current) and current.id == user.id and owner_env_code:
            raise HTTPException(
                status_code=403,
                detail="کد حساب Owner از backend/.env کنترل می‌شود؛ از منوی سرور تغییر دهید",
            )

    user.code = code
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=204)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current: models.User = Depends(get_current_admin),
):
    if user_id == current.id:
        raise HTTPException(status_code=400, detail="خودت رو نمی‌تونی حذف کنی")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if models.is_owner(user) and not models.is_owner(current):
        raise HTTPException(
            status_code=403, detail="فقط Owner می‌تواند حساب Owner را حذف کند"
        )
    db.delete(user)
    db.commit()