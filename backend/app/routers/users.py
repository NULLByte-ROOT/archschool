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
    _: models.User = Depends(get_current_admin),
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

    user = models.User(
        username=username,
        code=code,
        is_admin=role == models.ROLE_ADMIN,
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
    _: models.User = Depends(get_current_admin),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    updates = data.model_dump(exclude_unset=True)
    if updates.get("username"):
        updates["username"] = normalize_username(updates["username"])
    if updates.get("code"):
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
    if "role" in updates and updates["role"] not in models.VALID_ROLES:
        raise HTTPException(status_code=400, detail="نقش نامعتبر است")

    for key, value in updates.items():
        setattr(user, key, value)

    # Keep the legacy `is_admin` flag and the RBAC `role` in sync so both the
    # old admin-only checks and the new role checks agree.
    if "role" in updates:
        user.is_admin = user.role == models.ROLE_ADMIN
    elif "is_admin" in updates:
        user.role = models.ROLE_ADMIN if user.is_admin else models.ROLE_MEMBER

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
    db.delete(user)
    db.commit()