from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from .. import models, schemas
from ..database import get_db
from ..dependencies import get_current_user

router = APIRouter()


@router.get("/", response_model=List[schemas.AssignmentOut])
def list_assignments(
    completed: Optional[bool] = Query(None),
    course: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current: models.User = Depends(get_current_user),
):
    q = db.query(models.Assignment).filter(models.Assignment.owner_id == current.id)
    if completed is not None:
        q = q.filter(models.Assignment.completed == completed)
    if course:
        q = q.filter(models.Assignment.course == course)
    return q.order_by(models.Assignment.created_at.desc()).all()


@router.get("/{assignment_id}", response_model=schemas.AssignmentOut)
def get_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    current: models.User = Depends(get_current_user),
):
    obj = (
        db.query(models.Assignment)
        .filter(
            models.Assignment.id == assignment_id,
            models.Assignment.owner_id == current.id,
        )
        .first()
    )
    if not obj:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return obj


@router.post("/", response_model=schemas.AssignmentOut, status_code=201)
def create_assignment(
    data: schemas.AssignmentCreate,
    db: Session = Depends(get_db),
    current: models.User = Depends(get_current_user),
):
    obj = models.Assignment(**data.model_dump(), owner_id=current.id)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/{assignment_id}", response_model=schemas.AssignmentOut)
def update_assignment(
    assignment_id: int,
    data: schemas.AssignmentUpdate,
    db: Session = Depends(get_db),
    current: models.User = Depends(get_current_user),
):
    obj = (
        db.query(models.Assignment)
        .filter(
            models.Assignment.id == assignment_id,
            models.Assignment.owner_id == current.id,
        )
        .first()
    )
    if not obj:
        raise HTTPException(status_code=404, detail="Assignment not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(obj, key, value)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/{assignment_id}", status_code=204)
def delete_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    current: models.User = Depends(get_current_user),
):
    obj = (
        db.query(models.Assignment)
        .filter(
            models.Assignment.id == assignment_id,
            models.Assignment.owner_id == current.id,
        )
        .first()
    )
    if not obj:
        raise HTTPException(status_code=404, detail="Assignment not found")
    db.delete(obj)
    db.commit()