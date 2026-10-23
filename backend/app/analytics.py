"""Team analytics: completion percentage, streaks and seven-day activity.

The whole class is tiny (a single school team), so every aggregate is computed
from the tables on demand instead of being cached in denormalised columns. That
keeps one source of truth: deleting a completion immediately fixes every
percentage and streak, and there is no background job to keep in sync.

Days are bucketed on the school's wall clock (``SCHOOL_UTC_OFFSET_HOURS``), not
on the container's UTC clock, otherwise a completion at 01:00 local time would
be counted on the previous day and break someone's streak.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy.orm import Session

from . import models
from .config import settings

ONE_DAY = timedelta(days=1)


def utc_now() -> datetime:
    """Naive UTC timestamp — the format every column in this project stores."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def school_now() -> datetime:
    """Naive wall-clock timestamp in the school's timezone."""
    return utc_now() + timedelta(hours=settings.SCHOOL_UTC_OFFSET_HOURS)


def school_date(value: datetime) -> date:
    """Calendar day a stored UTC timestamp belongs to, in school time."""
    return (value + timedelta(hours=settings.SCHOOL_UTC_OFFSET_HOURS)).date()


def date_key(value: datetime) -> str:
    return school_date(value).isoformat()


def weekly_keys(days: int = 7) -> list[str]:
    """ISO dates of the last ``days`` school days, oldest first."""
    today = school_now().date()
    return [
        (today - timedelta(days=offset)).isoformat()
        for offset in range(days - 1, -1, -1)
    ]


def streak_from_days(day_keys: Iterable[str]) -> tuple[int, int]:
    """Return ``(current_streak, best_streak)`` from a set of ISO day keys.

    ``current_streak`` is the run ending today, or ending yesterday when today
    has no completion yet (the day is still available, so the streak is not
    broken). Any older gap resets it to zero. ``best_streak`` is the longest run
    of consecutive days in the user's whole history and never depends on today.
    """
    today = school_now().date()
    days = sorted(
        {
            date.fromisoformat(key)
            for key in day_keys
            if key and date.fromisoformat(key) <= today
        }
    )
    if not days:
        return 0, 0

    best = 1
    run = 1
    for previous, current in zip(days, days[1:]):
        run = run + 1 if (current - previous) == ONE_DAY else 1
        if run > best:
            best = run

    if today in days:
        cursor = today
    elif (today - ONE_DAY) in days:
        cursor = today - ONE_DAY
    else:
        return 0, best

    current_streak = 0
    while cursor in days:
        current_streak += 1
        cursor -= ONE_DAY
    return current_streak, max(best, current_streak)


def _subject_label(assignment: models.Assignment) -> str:
    """Human label used for strongest/weakest subject.

    ``course`` already stores the Persian subject name (the assignment form
    fills it from the timetable), so it is preferred over the raw slug.
    """
    return (assignment.course or "").strip() or (assignment.subject_id or "").strip() or "بدون درس"


def _load(db: Session):
    users = (
        db.query(models.User)
        .filter(models.User.is_active.is_(True))
        .order_by(models.User.username.asc())
        .all()
    )
    assignments = db.query(models.Assignment).all()
    completions = db.query(models.AssignmentCompletion).all()
    return users, assignments, completions


def build_leaderboard(db: Session) -> tuple[list[dict], dict]:
    """Return ranked per-user stats plus team-wide aggregates.

    Each entry is a plain dict shaped like ``schemas.LeaderboardEntryOut`` (the
    ``user`` value is still an ORM object; routers validate it). Ranking is
    strictly by ``completion_percentage``; ties are broken by the earlier
    ``last_completion_time`` (the person who finished first ranks higher).
    """
    users, assignments, completions = _load(db)
    active_ids = {user.id for user in users}
    # Inactive accounts keep their rows (for a possible re-activation) but must
    # not inflate the class trend or the class percentage.
    active_completions = [
        row for row in completions if row.user_id in active_ids
    ]
    total_assignments = len(assignments)
    assignment_by_id = {assignment.id: assignment for assignment in assignments}

    completions_by_user: dict[int, list[models.AssignmentCompletion]] = defaultdict(list)
    for completion in active_completions:
        completions_by_user[completion.user_id].append(completion)

    # Absolute subject sizes (every assignment in the class workspace).
    subject_totals: Counter[str] = Counter(
        _subject_label(assignment) for assignment in assignments
    )

    keys = weekly_keys()
    today_key = school_now().date().isoformat()

    entries: list[dict] = []
    for user in users:
        rows = completions_by_user.get(user.id, [])
        completed_count = len(rows)

        percentage = (
            round(completed_count * 100.0 / total_assignments, 1)
            if total_assignments
            else 0.0
        )

        completion_times = [row.completed_at for row in rows if row.completed_at]
        last_completion_time = max(completion_times) if completion_times else None

        speeds: list[float] = []
        subject_completed: Counter[str] = Counter()
        for row in rows:
            assignment = assignment_by_id.get(row.assignment_id)
            if assignment is None:
                continue
            subject_completed[_subject_label(assignment)] += 1
            if not row.completed_at or not assignment.created_at:
                continue
            hours = (
                row.completed_at - assignment.created_at
            ).total_seconds() / 3600.0
            if hours >= 0:
                speeds.append(hours)

        average_speed = round(sum(speeds) / len(speeds), 1) if speeds else None

        day_counts = Counter(date_key(value) for value in completion_times)
        weekly_activity = [
            {"date": key, "count": day_counts.get(key, 0)} for key in keys
        ]

        current_streak, best_streak = streak_from_days(day_counts.keys())

        ratios = [
            (
                subject_completed.get(label, 0) / total,
                subject_completed.get(label, 0),
                label,
            )
            for label, total in subject_totals.items()
            if total
        ]
        strongest = weakest = None
        if ratios:
            best_subject = max(ratios, key=lambda item: (item[0], item[1], item[2]))
            worst_subject = min(ratios, key=lambda item: (item[0], item[1], item[2]))
            if best_subject[0] > 0:
                strongest = best_subject[2]
            # Only call a subject "weak" when it is genuinely behind the best.
            if worst_subject[0] < best_subject[0]:
                weakest = worst_subject[2]

        entries.append(
            {
                "user": user,
                "rank": 0,
                "completion_percentage": percentage,
                "completed_count": completed_count,
                "total_assignments": total_assignments,
                "last_completion_time": last_completion_time,
                "average_speed_hours": average_speed,
                "weekly_activity": weekly_activity,
                "strongest_subject": strongest,
                "weakest_subject": weakest,
                "current_streak": current_streak,
                "best_streak": best_streak,
                "completed_today": day_counts.get(today_key, 0) > 0,
            }
        )

    # `datetime.max` pushes users with no completion to the bottom of a tie.
    entries.sort(
        key=lambda entry: (
            -entry["completion_percentage"],
            entry["last_completion_time"] or datetime.max,
            entry["user"].username.lower(),
        )
    )
    for index, entry in enumerate(entries, start=1):
        entry["rank"] = index

    completions_per_day = Counter(
        date_key(row.completed_at)
        for row in active_completions
        if row.completed_at
    )
    active_users = len(users)
    aggregates = {
        "team_record_streak": max(
            (entry["best_streak"] for entry in entries), default=0
        ),
        "total_assignments": total_assignments,
        "total_completions": len(active_completions),
        "active_users": active_users,
        "class_completion_percentage": (
            round(
                len(active_completions)
                * 100.0
                / (total_assignments * active_users),
                1,
            )
            if total_assignments and active_users
            else 0.0
        ),
        "weekly_trend": [
            {"date": key, "count": completions_per_day.get(key, 0)} for key in keys
        ],
    }
    return entries, aggregates


def find_entry(entries: list[dict], user_id: int) -> dict | None:
    for entry in entries:
        if entry["user"].id == user_id:
            return entry
    return None
