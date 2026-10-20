from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import models, schemas
from ..config import settings
from ..database import get_db
from ..dependencies import get_current_user
from ..storage import delete_upload, save_upload

router = APIRouter()


def _can_manage(assignment: models.Assignment, user: models.User) -> bool:
    """Admins and editors may manage any assignment; members only their own."""
    if user.is_admin or user.role in (models.ROLE_ADMIN, models.ROLE_EDITOR):
        return True
    return assignment.creator_id == user.id or assignment.owner_id == user.id


def _serialize(
    assignment: models.Assignment, current: models.User
) -> schemas.AssignmentOut:
    completer_ids = {c.user_id for c in assignment.completions}
    return schemas.AssignmentOut(
        id=assignment.id,
        title=assignment.title,
        description=assignment.description or "",
        course=assignment.course or "",
        category=assignment.category or "",
        subtype=assignment.subtype or "",
        subject_id=assignment.subject_id or "",
        due_date=assignment.due_date,
        completed=current.id in completer_ids,
        owner_id=assignment.owner_id,
        creator_id=assignment.creator_id,
        creator_username=assignment.creator.username if assignment.creator else None,
        completed_by_users=[
            schemas.CompletedByUser(
                id=completion.user_id,
                username=completion.user.username if completion.user else None,
            )
            for completion in assignment.completions
        ],
        is_completed_by_me=current.id in completer_ids,
        created_at=assignment.created_at,
        updated_at=assignment.updated_at,
    )


def _base_query(db: Session):
    return db.query(models.Assignment).options(
        selectinload(models.Assignment.creator),
        selectinload(models.Assignment.completions).selectinload(
            models.AssignmentCompletion.user
        ),
    )


def _get_or_404(db: Session, assignment_id: int) -> models.Assignment:
    obj = (
        _base_query(db)
        .filter(models.Assignment.id == assignment_id)
        .first()
    )
    if not obj:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return obj


def _toggle_completion(
    db: Session, assignment: models.Assignment, current: models.User
) -> None:
    """Toggle the current user's completion and (de)award their points."""
    existing = (
        db.query(models.AssignmentCompletion)
        .filter(
            models.AssignmentCompletion.user_id == current.id,
            models.AssignmentCompletion.assignment_id == assignment.id,
        )
        .first()
    )
    if existing:
        db.delete(existing)
        current.points = max(0, (current.points or 0) - settings.POINTS_PER_ASSIGNMENT)
    else:
        db.add(
            models.AssignmentCompletion(
                user_id=current.id,
                assignment_id=assignment.id,
            )
        )
        current.points = (current.points or 0) + settings.POINTS_PER_ASSIGNMENT


@router.get("/", response_model=List[schemas.AssignmentOut])
def list_assignments(
    completed: Optional[bool] = Query(None),
    course: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current: models.User = Depends(get_current_user),
):
    # Assignments are public in the team workspace: everyone sees everything.
    q = _base_query(db)
    if completed is not None:
        mine = select(models.AssignmentCompletion.assignment_id).where(
            models.AssignmentCompletion.user_id == current.id
        )
        if completed:
            q = q.filter(models.Assignment.id.in_(mine))
        else:
            q = q.filter(~models.Assignment.id.in_(mine))
    if course:
        q = q.filter(models.Assignment.course == course)
    return [
        _serialize(obj, current)
        for obj in q.order_by(models.Assignment.created_at.desc()).all()
    ]


@router.get("/{assignment_id}", response_model=schemas.AssignmentOut)
def get_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    current: models.User = Depends(get_current_user),
):
    return _serialize(_get_or_404(db, assignment_id), current)


@router.get("/{assignment_id}/team", response_model=List[schemas.TeamMemberOut])
def assignment_team(
    assignment_id: int,
    db: Session = Depends(get_db),
    current: models.User = Depends(get_current_user),
):
    assignment = _get_or_404(db, assignment_id)

    completed_user_ids = {completion.user_id for completion in assignment.completions}

    users = (
        db.query(models.User)
        .filter(models.User.is_active.is_(True))
        .order_by(models.User.points.desc(), models.User.username.asc())
        .all()
    )

    return [
        schemas.TeamMemberOut(
            user=schemas.PublicUserOut.model_validate(user),
            completed=user.id in completed_user_ids,
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
    _get_or_404(db, assignment_id)
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
    _get_or_404(db, assignment_id)

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
    completed = bool(payload.pop("completed", False))
    obj = models.Assignment(
        **payload,
        owner_id=current.id,
        creator_id=current.id,
        completed=completed,
        points_awarded=completed,
    )
    db.add(obj)
    db.flush()
    if completed:
        db.add(
            models.AssignmentCompletion(
                user_id=current.id,
                assignment_id=obj.id,
            )
        )
        current.points = (current.points or 0) + settings.POINTS_PER_ASSIGNMENT
    db.commit()
    return _serialize(_get_or_404(db, obj.id), current)


@router.patch("/{assignment_id}", response_model=schemas.AssignmentOut)
def update_assignment(
    assignment_id: int,
    data: schemas.AssignmentUpdate,
    db: Session = Depends(get_db),
    current: models.User = Depends(get_current_user),
):
    obj = _get_or_404(db, assignment_id)
    if not _can_manage(obj, current):
        raise HTTPException(
            status_code=403, detail="شما اجازهٔ ویرایش این تکلیف را ندارید"
        )

    updates = data.model_dump(exclude_unset=True)
    # Completion is per-user and handled through the toggle endpoint; keep it
    # working here too for backwards compatibility with older clients.
    if "completed" in updates:
        completed = updates.pop("completed")
        currently_mine = any(c.user_id == current.id for c in obj.completions)
        if completed is not None and bool(completed) != currently_mine:
            _toggle_completion(db, obj, current)

    for key, value in updates.items():
        setattr(obj, key, value)
    db.commit()
    return _serialize(_get_or_404(db, assignment_id), current)


@router.patch("/{assignment_id}/toggle", response_model=schemas.AssignmentOut)
def toggle_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    current: models.User = Depends(get_current_user),
):
    """Toggle the completion status of this assignment for the current user."""
    obj = _get_or_404(db, assignment_id)
    _toggle_completion(db, obj, current)
    db.commit()
    return _serialize(_get_or_404(db, assignment_id), current)


@router.delete("/{assignment_id}", status_code=204)
def delete_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    current: models.User = Depends(get_current_user),
):
    obj = _get_or_404(db, assignment_id)
    if not _can_manage(obj, current):
        raise HTTPException(
            status_code=403, detail="شما اجازهٔ حذف این تکلیف را ندارید"
        )
    for attachment in list(obj.attachments):
        delete_upload(attachment.file_url)
    db.delete(obj)
    db.commit()
