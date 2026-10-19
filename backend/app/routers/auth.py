from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..config import settings
from ..database import get_db
from ..security import create_access_token, generate_code

router = APIRouter()


@router.post("/login", response_model=schemas.LoginResponse)
def login(data: schemas.LoginRequest, db: Session = Depends(get_db)):
    code = data.code.upper()

    if code == settings.ADMIN_CODE:
        user = db.query(models.User).filter(models.User.username == data.username).first()
        if not user:
            user = models.User(
                username=data.username,
                code=generate_code(),
                is_admin=True,
                is_active=True,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        elif not user.is_admin:
            raise HTTPException(status_code=403, detail="Username taken")
    else:
        user = (
            db.query(models.User)
            .filter(models.User.username == data.username, models.User.code == code)
            .first()
        )
        if not user:
            raise HTTPException(status_code=401, detail="نام کاربری یا کد اشتباه است")
        if not user.is_active:
            raise HTTPException(status_code=403, detail="حساب غیرفعال است")

    token = create_access_token({"sub": str(user.id), "is_admin": user.is_admin})
    return schemas.LoginResponse(access_token=token, user=user)