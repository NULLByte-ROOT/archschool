from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..dependencies import get_current_admin, get_current_user

router = APIRouter()


def _load_periods(db: Session) -> list[models.SchoolSchedule]:
    return (
        db.query(models.SchoolSchedule)
        .order_by(models.SchoolSchedule.period_number)
        .all()
    )


def _out(periods: list[models.SchoolSchedule]) -> schemas.SchoolScheduleOut:
    return schemas.SchoolScheduleOut(
        periods=[
            schemas.SchoolPeriodIn(
                period_number=p.period_number,
                start_time=p.start_time,
                end_time=p.end_time,
            )
            for p in periods
        ]
    )


def _validate(update: schemas.SchoolScheduleUpdate) -> None:
    """Reject times that cannot describe a real school day.

    A period may not end before it starts, and periods may not overlap; they
    may however touch (one period's start == the previous period's end), which
    is how the default 08:00-14:00 day is built.
    """
    periods = sorted(update.periods, key=lambda p: p.period_number)
    numbers = [p.period_number for p in periods]
    if numbers != [1, 2, 3, 4]:
        raise HTTPException(
            status_code=422,
            detail="باید دقیقاً ۴ زنگ با شماره‌های ۱ تا ۴ ارسال شود",
        )
    for p in periods:
        start = _to_minutes(p.start_time)
        end = _to_minutes(p.end_time)
        if end <= start:
            raise HTTPException(
                status_code=422,
                detail=f"زنگ {p.period_number}: ساعت پایان باید بعد از ساعت شروع باشد",
            )
    for prev, cur in zip(periods, periods[1:]):
        if _to_minutes(cur.start_time) < _to_minutes(prev.end_time):
            raise HTTPException(
                status_code=422,
                detail=f"زنگ {cur.period_number} با زنگ قبلی تداخل دارد",
            )


def _to_minutes(t: str) -> int:
    hours, minutes = t.split(":")
    return int(hours) * 60 + int(minutes)


@router.get("", response_model=schemas.SchoolScheduleOut)
def read_school_schedule(
    db: Session = Depends(get_db),
    _user: models.User = Depends(get_current_user),
):
    """Bell times used by countdowns and the timetable. Every signed-in user."""
    periods = _load_periods(db)
    if periods:
        return _out(periods)

    # Table not yet seeded (fresh deploy racing the boot migration): fall back
    # to the built-in default day instead of failing the client.
    return schemas.SchoolScheduleOut(
        periods=[
            schemas.SchoolPeriodIn(
                period_number=number,
                start_time=start,
                end_time=end,
            )
            for number, (start, end) in enumerate(
                [
                    ("08:00", "09:30"),
                    ("09:30", "11:00"),
                    ("11:00", "12:30"),
                    ("12:30", "14:00"),
                ],
                start=1,
            )
        ]
    )


@router.put("", response_model=schemas.SchoolScheduleOut)
def update_school_schedule(
    update: schemas.SchoolScheduleUpdate,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(get_current_admin),
):
    """Replace all four periods atomically. Admin only."""
    _validate(update)

    existing = {p.period_number: p for p in _load_periods(db)}
    for period in sorted(update.periods, key=lambda p: p.period_number):
        row = existing.get(period.period_number)
        if row:
            row.start_time = period.start_time
            row.end_time = period.end_time
        else:
            db.add(
                models.SchoolSchedule(
                    period_number=period.period_number,
                    start_time=period.start_time,
                    end_time=period.end_time,
                )
            )
    db.commit()

    return _out(_load_periods(db))
