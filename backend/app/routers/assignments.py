import math
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import models, notifications, schemas
from ..config import settings
from ..database import get_db
from ..dependencies import get_current_user
from ..storage import delete_upload, save_upload

router = APIRouter()

MANAGE_DETAIL = "فقط ادمین می‌تواند تکلیف بسازد یا ویرایش کند"


def _can_manage(assignment: models.Assignment, user: models.User) -> bool:
    """Admins and owners manage every assignment.

    Under the new RBAC members create/edit nothing (read-only); their only
    write action is toggling their own completion via the dedicated endpoint.
    """
    return models.is_staff(user)


def _require_staff(user: models.User) -> None:
    if not models.is_staff(user):
        raise HTTPException(status_code=403, detail=MANAGE_DETAIL)


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


def _ensure_completion_delay(
    assignment: models.Assignment, now: datetime
) -> None:
    """Reject "Done" before the assignment had time to be done.

    Guards against blanket-checking every task the instant it appears: a user
    must wait ``COMPLETION_DELAY_MINUTES`` from creation before marking it done.
    Un-marking is always allowed (it cannot inflate anyone's stats).
    """
    delay = timedelta(minutes=max(0, settings.COMPLETION_DELAY_MINUTES))
    if delay <= timedelta(0):
        return
    created_at = assignment.created_at or now
    remaining = delay - (now - created_at)
    if remaining > timedelta(0):
        minutes = max(1, math.ceil(remaining.total_seconds() / 60))
        raise HTTPException(
            status_code=400,
            detail=(
                "برای جلوگیری از تقلب، تا "
                f"{minutes} دقیقهٔ دیگر نمی‌توانید این تکلیف را "
                "انجام‌شده علامت بزنید."
            ),
        )


def _guard_toggle_attempt(
    db: Session,
    assignment: models.Assignment,
    current: models.User,
    now: datetime,
) -> None:
    """Rate-limit repeated toggles of one assignment.

    More than ``TOGGLE_LIMIT_PER_HOUR`` attempts inside a rolling hour lock the
    toggle for ``TOGGLE_LOCK_MINUTES``. The lock is committed *before* raising:
    the request session would otherwise roll back the very row that has to make
    the punishment stick.
    """
    guard = (
        db.query(models.CompletionToggleGuard)
        .filter(
            models.CompletionToggleGuard.user_id == current.id,
            models.CompletionToggleGuard.assignment_id == assignment.id,
        )
        .first()
    )
    if guard is None:
        guard = models.CompletionToggleGuard(
            user_id=current.id,
            assignment_id=assignment.id,
            window_started_at=now,
            attempt_count=0,
        )
        db.add(guard)

    if guard.locked_until and guard.locked_until > now:
        minutes = max(
            1, math.ceil((guard.locked_until - now).total_seconds() / 60)
        )
        raise HTTPException(
            status_code=429,
            detail=(
                "تغییر وضعیت این تکلیف موقتاً قفل شده است. "
                f"{minutes} دقیقهٔ دیگر دوباره تلاش کنید."
            ),
        )

    window = timedelta(hours=1)
    if guard.window_started_at is None or now - guard.window_started_at >= window:
        guard.window_started_at = now
        guard.attempt_count = 0
        guard.locked_until = None

    guard.attempt_count = (guard.attempt_count or 0) + 1
    guard.updated_at = now

    if guard.attempt_count > settings.TOGGLE_LIMIT_PER_HOUR:
        guard.locked_until = now + timedelta(
            minutes=max(1, settings.TOGGLE_LOCK_MINUTES)
        )
        db.commit()
        raise HTTPException(
            status_code=429,
            detail=(
                "تعداد تغییر وضعیت این تکلیف بیش از حد مجاز بود؛ "
                f"تا {max(1, settings.TOGGLE_LOCK_MINUTES)} دقیقهٔ دیگر قفل است."
            ),
        )


def _toggle_completion(
    db: Session,
    assignment: models.Assignment,
    current: models.User,
    now: Optional[datetime] = None,
) -> None:
    """Toggle the current user's completion, enforcing the anti-cheat rules."""
    now = now or datetime.utcnow()
    existing = (
        db.query(models.AssignmentCompletion)
        .filter(
            models.AssignmentCompletion.user_id == current.id,
            models.AssignmentCompletion.assignment_id == assignment.id,
        )
        .first()
    )
    # The 30-minute rule only protects the "mark as done" direction.
    if existing is None:
        _ensure_completion_delay(assignment, now)
    _guard_toggle_attempt(db, assignment, current, now)
    if existing:
        db.delete(existing)
    else:
        db.add(
            models.AssignmentCompletion(
                user_id=current.id,
                assignment_id=assignment.id,
                completed_at=now,
            )
        )


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
        .order_by(models.User.username.asc())
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
    _require_staff(current)
    payload = data.model_dump()
    completed = bool(payload.pop("completed", False))
    obj = models.Assignment(
        **payload,
        owner_id=current.id,
        creator_id=current.id,
        completed=completed,
    )
    db.add(obj)
    db.flush()
    if completed:
        # Staff may create an assignment that is already done; the creation
        # delay intentionally does not apply to this initial state.
        db.add(
            models.AssignmentCompletion(
                user_id=current.id,
                assignment_id=obj.id,
            )
        )
    db.commit()
    created = _get_or_404(db, obj.id)
    result = _serialize(created, current)
    notifications.notify_new_assignment(db, created)
    return result


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
