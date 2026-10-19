from datetime import datetime, time, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from .. import models, schemas
from ..config import settings
from ..database import get_db
from ..dependencies import get_current_user
from ..storage import delete_upload, save_upload

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
        .filter(models.Assignment.id == assignment_id)
        .first()
    )
    if not obj:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return obj


@router.get("/{assignment_id}/team", response_model=List[schemas.TeamMemberOut])
def assignment_team(
    assignment_id: int,
    db: Session = Depends(get_db),
    current: models.User = Depends(get_current_user),
):
    assignment = (
        db.query(models.Assignment)
        .filter(models.Assignment.id == assignment_id)
        .first()
    )
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    matching = db.query(models.Assignment.owner_id).filter(
        models.Assignment.completed.is_(True)
    )
    if assignment.subject_id:
        matching = matching.filter(
            models.Assignment.subject_id == assignment.subject_id
        )
    if assignment.category:
        matching = matching.filter(models.Assignment.category == assignment.category)
    if assignment.subtype:
        matching = matching.filter(models.Assignment.subtype == assignment.subtype)
    if assignment.due_date:
        day_start = datetime.combine(assignment.due_date.date(), time.min)
        day_end = day_start + timedelta(days=1)
        matching = matching.filter(
            models.Assignment.due_date >= day_start,
            models.Assignment.due_date < day_end,
        )
    else:
        matching = matching.filter(models.Assignment.due_date.is_(None))
    if not (assignment.subject_id or assignment.category or assignment.subtype):
        matching = matching.filter(models.Assignment.title == assignment.title)

    completed_owner_ids = {owner_id for (owner_id,) in matching.all() if owner_id}
    if assignment.owner_id:
        if assignment.completed:
            completed_owner_ids.add(assignment.owner_id)
        else:
            completed_owner_ids.discard(assignment.owner_id)

    users = (
        db.query(models.User)
        .filter(models.User.is_active.is_(True))
        .order_by(models.User.points.desc(), models.User.username.asc())
        .all()
    )

    return [
        schemas.TeamMemberOut(
            user=schemas.PublicUserOut.model_validate(user),
            completed=user.id in completed_owner_ids,
            is_self=user.id == current.id,
        )
        for user in users
    ]


@router.get(
    "/{assignment_id}/attachments", response_model=List[schemas.AttachmentOut]
)
def list_attachments(
    assignment_id: int,
    db: Session = Depends(get_db),
    current: models.User = Depends(get_current_user),
):
    assignment = (
        db.query(models.Assignment)
        .filter(models.Assignment.id == assignment_id)
        .first()
    )
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return (
        db.query(models.Attachment)
        .filter(models.Attachment.assignment_id == assignment_id)
        .order_by(models.Attachment.created_at.desc())
        .all()
    )


@router.post(
    "/{assignment_id}/attachments",
    response_model=schemas.AttachmentOut,
    status_code=201,
)
async def upload_attachment(
    assignment_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current: models.User = Depends(get_current_user),
):
    assignment = (
        db.query(models.Assignment)
        .filter(models.Assignment.id == assignment_id)
        .first()
    )
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    url, file_name, _ = await save_upload(file)
    attachment = models.Attachment(
        assignment_id=assignment_id,
        user_id=current.id,
        file_url=url,
        file_name=file_name,
    )
    current.points = (current.points or 0) + settings.POINTS_PER_UPLOAD
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    return attachment


@router.post("/", response_model=schemas.AssignmentOut, status_code=201)
def create_assignment(
    data: schemas.AssignmentCreate,
    db: Session = Depends(get_db),
    current: models.User = Depends(get_current_user),
):
    payload = data.model_dump()
    points_awarded = bool(payload.get("completed"))
    obj = models.Assignment(
        **payload,
        owner_id=current.id,
        points_awarded=points_awarded,
    )
    if points_awarded:
        current.points = (current.points or 0) + 10
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

    updates = data.model_dump(exclude_unset=True)
    if updates.get("completed") is True and not obj.completed and not obj.points_awarded:
        obj.points_awarded = True
        current.points = (current.points or 0) + 10

    for key, value in updates.items():
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
    for attachment in list(obj.attachments):
        delete_upload(attachment.file_url)
    db.delete(obj)
    db.commit()
