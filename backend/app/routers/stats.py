"""Team statistics: percentage-based leaderboard, streaks and dashboard data."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import analytics, models, schemas
from ..database import get_db
from ..dependencies import get_current_user

router = APIRouter()

USER_NOT_FOUND = "کاربر پیدا نشد"


def _entry(entry: dict) -> schemas.LeaderboardEntryOut:
    """Validate one analytics dict into the public response model."""
    return schemas.LeaderboardEntryOut(
        user=schemas.PublicUserOut.model_validate(entry["user"]),
        rank=entry["rank"],
        completion_percentage=entry["completion_percentage"],
        completed_count=entry["completed_count"],
        total_assignments=entry["total_assignments"],
        upload_count=entry.get("upload_count", 0),
        last_completion_time=entry["last_completion_time"],
        average_speed_hours=entry["average_speed_hours"],
        weekly_activity=[
            schemas.DailyActivityOut(**point) for point in entry["weekly_activity"]
        ],
        strongest_subject=entry["strongest_subject"],
        weakest_subject=entry["weakest_subject"],
        current_streak=entry["current_streak"],
        best_streak=entry["best_streak"],
        completed_today=entry["completed_today"],
        streak_at_risk=entry.get("streak_at_risk", False),
    )


@router.get("/leaderboard", response_model=List[schemas.LeaderboardEntryOut])
def leaderboard(
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    """Ranked strictly by completion percentage.

    Tie-break: whoever reached their percentage earlier (an earlier
    ``last_completion_time``) ranks higher. Users without any completion fall to
    the bottom.
    """
    entries, _aggregates = analytics.build_leaderboard(db)
    return [_entry(entry) for entry in entries]


@router.get("/overview", response_model=schemas.TeamOverviewOut)
def overview(
    db: Session = Depends(get_db),
    current: models.User = Depends(get_current_user),
):
    """Everything the home dashboard renders, in a single round-trip."""
    entries, aggregates = analytics.build_leaderboard(db)
    me = analytics.find_entry(entries, current.id)
    if me is None:
        raise HTTPException(status_code=404, detail=USER_NOT_FOUND)

    return schemas.TeamOverviewOut(
        me=_entry(me),
        top_users=[_entry(entry) for entry in entries[:3]],
        team_record_streak=aggregates["team_record_streak"],
        total_assignments=aggregates["total_assignments"],
        total_completions=aggregates["total_completions"],
        active_users=aggregates["active_users"],
        class_completion_percentage=aggregates["class_completion_percentage"],
        weekly_trend=[
            schemas.DailyActivityOut(**point)
            for point in aggregates["weekly_trend"]
        ],
    )


@router.get("/users/{user_id}", response_model=schemas.LeaderboardEntryOut)
def user_stats(
    user_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    """Full stats for one user — powers the profile modal."""
    entries, _aggregates = analytics.build_leaderboard(db)
    entry = analytics.find_entry(entries, user_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=USER_NOT_FOUND)
    return _entry(entry)
