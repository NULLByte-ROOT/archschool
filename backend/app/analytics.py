"""Team analytics: completion percentage, streaks and seven-day activity.

The whole class is tiny (a single school team), so every aggregate is computed
from the tables on demand instead of being cached in denormalised columns.

Streaks and the seven-day history read the delete-safe ``daily_activity``
ledger (written on every explicit toggle, never touched by assignment
deletion), merged with the live ``assignment_completions`` rows. Percentages
stay live: deleting an assignment immediately fixes them.

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

# Each attachment a user uploaded to a live assignment is worth this many bonus
# percentage points. The bonus is additive on top of the completion ratio and
# the whole percentage is capped at 100 (see ``compute_user_stats``).
UPLOAD_BONUS_PERCENT = 5.0

# The streak is not reset at noon; the UI only starts warning after 12:00 local
# school time when the user has not completed anything that day.
STREAK_AT_RISK_MINUTE = 12 * 60

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


class _StatsContext:
    """Everything the per-user formula needs, queried once per request.

    ``all_completions`` is only used for the delete-safe streak history; the
    percentage itself is computed exclusively from rows whose assignment is not
    soft-deleted, so deleting a task immediately removes it from the denominator
    (and from every user's completed count) instead of leaving a ghost task.
    """

    __slots__ = (
        "users",
        "live_assignments",
        "all_completions",
        "live_completions",
        "attachments",
        "assignment_by_id",
        "completions_by_user",
        "attachments_by_user",
        "activity_by_user",
        "subject_totals",
        "total_assignments",
        "keys",
        "today_key",
    )

    def __init__(self, db: Session) -> None:
        self.users = (
            db.query(models.User)
            .filter(models.User.is_active.is_(True))
            .order_by(models.User.username.asc())
            .all()
        )
        active_ids = {user.id for user in self.users}

        all_assignments = db.query(models.Assignment).all()
        self.live_assignments = [
            assignment
            for assignment in all_assignments
            if assignment.deleted_at is None
        ]
        self.assignment_by_id = {
            assignment.id: assignment for assignment in self.live_assignments
        }
        live_ids = set(self.assignment_by_id)

        # Keep every completion for streak/history, but only the live ones can
        # contribute to the percentage and to the "X of Y" counter.
        self.all_completions = db.query(models.AssignmentCompletion).all()
        self.live_completions = [
            row
            for row in self.all_completions
            if row.user_id in active_ids and row.assignment_id in live_ids
        ]

        self.attachments = [
            attachment
            for attachment in db.query(models.Attachment).all()
            if attachment.user_id in active_ids
            and attachment.assignment_id in live_ids
        ]

        self.completions_by_user: dict[
            int, list[models.AssignmentCompletion]
        ] = defaultdict(list)
        for completion in self.live_completions:
            self.completions_by_user[completion.user_id].append(completion)

        self.attachments_by_user: Counter[int] = Counter(
            attachment.user_id for attachment in self.attachments
        )

        self.activity_by_user: dict[int, Counter[str]] = defaultdict(Counter)
        for row in db.query(models.DailyActivity).all():
            if row.user_id not in active_ids or not row.completions:
                continue
            key = (
                row.activity_date.isoformat()
                if hasattr(row.activity_date, "isoformat")
                else str(row.activity_date)[:10]
            )
            self.activity_by_user[row.user_id][key] += row.completions

        self.subject_totals: Counter[str] = Counter(
            _subject_label(assignment) for assignment in self.live_assignments
        )
        self.total_assignments = len(self.live_assignments)
        self.keys = weekly_keys()
        self.today_key = school_now().date().isoformat()


def _streak_at_risk(completed_today: bool) -> bool:
    """Warning flag for the dashboard, computed on the fly.

    The streak counter itself is never reset at noon. Only after 12:00 on the
    school's wall clock does an empty day turn the hero widget red. Before noon
    the user still has time, so no warning is shown.
    """
    if completed_today:
        return False
    wall = school_now()
    return (wall.hour * 60 + wall.minute) >= STREAK_AT_RISK_MINUTE


def compute_user_stats(
    db: Session,
    user_id: int,
    *,
    context: _StatsContext | None = None,
) -> dict | None:
    """The single source of truth for one user's percentage and streaks.

    Formula (shared by the leaderboard, the profile modal and the assignments
    dashboard):

        percentage = min(100, completed / total * 100 + uploads * 5)

    - ``total`` counts every non-deleted assignment, overdue ones included.
    - ``completed`` counts this user's completion rows for those assignments.
    - ``uploads`` counts every attachment this user uploaded to a live task.

    Returns ``None`` for an unknown/inactive user.
    """
    ctx = context or _StatsContext(db)
    user = next((candidate for candidate in ctx.users if candidate.id == user_id), None)
    if user is None:
        return None

    rows = ctx.completions_by_user.get(user_id, [])
    completed_count = len(rows)
    upload_count = ctx.attachments_by_user.get(user_id, 0)

    percentage = 0.0
    if ctx.total_assignments:
        percentage = completed_count * 100.0 / ctx.total_assignments
    percentage = round(
        min(100.0, percentage + upload_count * UPLOAD_BONUS_PERCENT), 1
    )

    completion_times = [row.completed_at for row in rows if row.completed_at]
    last_completion_time = max(completion_times) if completion_times else None

    speeds: list[float] = []
    subject_completed: Counter[str] = Counter()
    for row in rows:
        assignment = ctx.assignment_by_id.get(row.assignment_id)
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

    live_counts = Counter(date_key(value) for value in completion_times)
    history = ctx.activity_by_user.get(user_id, Counter())
    # max(), not sum: the ledger and the live completions describe the same
    # events, and during a blue-green deploy one slot may have written only one
    # of the two. Taking the larger also keeps deleted work in history.
    day_counts = Counter(
        {
            key: max(live_counts.get(key, 0), history.get(key, 0))
            for key in set(live_counts) | set(history)
        }
    )
    weekly_activity = [
        {"date": key, "count": day_counts.get(key, 0)} for key in ctx.keys
    ]

    current_streak, best_streak = streak_from_days(day_counts.keys())

    ratios = [
        (
            subject_completed.get(label, 0) / total,
            subject_completed.get(label, 0),
            label,
        )
        for label, total in ctx.subject_totals.items()
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

    completed_today = day_counts.get(ctx.today_key, 0) > 0
    return {
        "user": user,
        "rank": 0,
        "completion_percentage": percentage,
        "completed_count": completed_count,
        "total_assignments": ctx.total_assignments,
        "upload_count": upload_count,
        "last_completion_time": last_completion_time,
        "average_speed_hours": average_speed,
        "weekly_activity": weekly_activity,
        "strongest_subject": strongest,
        "weakest_subject": weakest,
        "current_streak": current_streak,
        "best_streak": best_streak,
        "completed_today": completed_today,
        "streak_at_risk": _streak_at_risk(completed_today),
    }


def build_leaderboard(db: Session) -> tuple[list[dict], dict]:
    """Return ranked per-user stats plus team-wide aggregates.

    Every entry is produced by :func:`compute_user_stats` with one shared
    :class:`_StatsContext`, so the leaderboard, the dashboard overview and the
    profile endpoint can never disagree about a user's percentage.
    """
    ctx = _StatsContext(db)

    entries: list[dict] = []
    trend_by_day: Counter[str] = Counter()
    for user in ctx.users:
        entry = compute_user_stats(db, user.id, context=ctx)
        if entry is None:
            continue
        entries.append(entry)
        for point in entry["weekly_activity"]:
            trend_by_day[point["date"]] += point["count"]

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

    active_users = len(ctx.users)
    aggregates = {
        "team_record_streak": max(
            (entry["best_streak"] for entry in entries), default=0
        ),
        "total_assignments": ctx.total_assignments,
        "total_completions": len(ctx.live_completions),
        "active_users": active_users,
        "class_completion_percentage": (
            round(
                min(
                    100.0,
                    len(ctx.live_completions)
                    * 100.0
                    / (ctx.total_assignments * active_users),
                ),
                1,
            )
            if ctx.total_assignments and active_users
            else 0.0
        ),
        "weekly_trend": [
            {"date": key, "count": trend_by_day.get(key, 0)} for key in ctx.keys
        ],
    }
    return entries, aggregates


def find_entry(entries: list[dict], user_id: int) -> dict | None:
    for entry in entries:
        if entry["user"].id == user_id:
            return entry
    return None
