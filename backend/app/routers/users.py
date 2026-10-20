from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from .. import models, schemas
from ..database import get_db
from ..dependencies import get_current_admin, get_current_user
from ..security import generate_code

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
    if db.query(models.User).filter(models.User.username == data.username).first():
        raise HTTPException(status_code=400, detail="این نام کاربری قبلاً گرفته شده")

    code = (data.code or generate_code()).upper()

    role = data.role or (models.ROLE_ADMIN if data.is_admin else models.ROLE_MEMBER)
    if role not in models.VALID_ROLES:
        raise HTTPException(status_code=400, detail="نقش نامعتبر است")

    user = models.User(
        username=data.username,
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
    if updates.get("code"):
        updates["code"] = updates["code"].upper()
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