"""Push fan-out for chat, new assignments and approaching deadlines.

Kept in one module so the audience rules live next to the permission rules they
mirror:

* a private message reaches only its receiver;
* assignment comments reach the whole team (members may comment there);
* the global room reaches only roles that can actually open it — members are
  chat-locked everywhere except assignment comment rooms, so pushing them into
  the global chat would deep-link to a blocked screen;
* a new assignment reaches every active account except its creator;
* a deadline reminder reaches only users who have not completed the task.

The deadline scheduler is a single asyncio loop started by the FastAPI lifespan.
It reserves ``deadline_notifications`` rows inside the database before sending,
so blue-green's two short-lived instances (and restarts) cannot double-send.
"""

from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime, timedelta
from typing import Any, Iterable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import models
from .config import settings
from .database import SessionLocal
from .push import dispatch_push, send_push

logger = logging.getLogger("archschool.notifications")

# Only these roles can open the global/DM chat surfaces (see routers/messages.py).
CHAT_ROLES = (models.ROLE_FRIEND, models.ROLE_ADMIN, models.ROLE_OWNER)

# Two reminders per task, in hours before the deadline.
DEADLINE_THRESHOLDS = (24, 2)

DEADLINE_TITLE = "مهلت نزدیک است"
ASSIGNMENT_TITLE = "تکلیف جدید"


# ---------------------------------------------------------------------------
#  Audience helpers
# ---------------------------------------------------------------------------
def tokens_for_users(
    db: Session, user_ids: Iterable[int], channel: str = "chat"
) -> list[str]:
    """Active Expo tokens of these users for one notification channel.

    The per-token switches saved from the mobile Settings page are applied here,
    before anything reaches Expo, so muting a channel costs zero requests.
    """
    ids = [int(user_id) for user_id in set(user_ids) if user_id]
    if not ids:
        return []
    channel_column = {
        "chat": models.PushToken.notify_chat,
        "assignments": models.PushToken.notify_assignments,
        "deadlines": models.PushToken.notify_deadlines,
    }.get(channel, models.PushToken.notify_chat)
    rows = (
        db.query(models.PushToken.token)
        .join(models.User, models.User.id == models.PushToken.user_id)
        .filter(
            models.PushToken.user_id.in_(ids),
            channel_column.is_(True),
            models.User.is_active.is_(True),
        )
        .all()
    )
    return [row[0] for row in rows if row and row[0]]


def _active_user_ids(
    db: Session,
    *,
    exclude: int | None = None,
    roles: Iterable[str] | None = None,
) -> list[int]:
    query = db.query(models.User.id).filter(models.User.is_active.is_(True))
    if exclude is not None:
        query = query.filter(models.User.id != exclude)
    if roles is not None:
        query = query.filter(models.User.role.in_(tuple(roles)))
    return [row[0] for row in query.all()]


def _preview(content: str, has_file: bool) -> str:
    text = (content or "").strip()
    if text:
        return text
    return "📷 تصویر" if has_file else "پیام جدید"


# ---------------------------------------------------------------------------
#  Chat
# ---------------------------------------------------------------------------
def notify_chat_message(
    db: Session,
    *,
    sender_id: int,
    sender_username: str | None,
    receiver_id: int | None,
    assignment_id: int | None,
    content: str,
    has_file: bool,
    message_id: int,
    assignment_title: str | None = None,
) -> None:
    """Push one freshly stored chat message to the people who can read it."""
    if not settings.PUSH_NOTIFICATIONS_ENABLED:
        return

    if receiver_id is not None:
        room = f"dm:{min(sender_id, receiver_id)}:{max(sender_id, receiver_id)}"
        recipients = [receiver_id]
    elif assignment_id is not None:
        room = f"assignment:{assignment_id}"
        recipients = _active_user_ids(db, exclude=sender_id)
    else:
        room = "global"
        recipients = _active_user_ids(db, exclude=sender_id, roles=CHAT_ROLES)

    tokens = tokens_for_users(db, recipients, channel="chat")
    if not tokens:
        return

    sender = sender_username or "همکلاسی"
    body = _preview(content, has_file)
    data: dict[str, Any] = {
        "type": "chat",
        "room": room,
        "message_id": message_id,
        "sender_id": sender_id,
    }
    if assignment_id is not None:
        data["assignment_id"] = assignment_id
        if assignment_title:
            data["assignment_title"] = assignment_title
            body = f"{body} · {assignment_title}"

    dispatch_push(tokens, sender, body, data, channel_id="chat")


# ---------------------------------------------------------------------------
#  New assignment
# ---------------------------------------------------------------------------
def _mark_initial_thresholds(db: Session, assignment: models.Assignment) -> None:
    """Treat the creation push as the reminder for thresholds already crossed.

    A task created two hours before its deadline should not immediately produce
    a second "24 hours left" notification. Marking every threshold at or above
    the remaining time keeps later reminders honest (the 2-hour one still fires
    for a task created 20 hours ahead) without duplicating the creation push.
    """
    if assignment.due_date is None:
        return
    remaining_hours = (
        assignment.due_date - datetime.utcnow()
    ).total_seconds() / 3600
    if remaining_hours < 0:
        return
    for threshold in DEADLINE_THRESHOLDS:
        if remaining_hours > threshold:
            continue
        db.add(
            models.DeadlineNotification(
                assignment_id=assignment.id, threshold_hours=threshold
            )
        )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
    except Exception:  # pragma: no cover - reminder bookkeeping is best effort
        db.rollback()
        logger.warning("Could not reserve initial deadline thresholds", exc_info=True)


def notify_new_assignment(db: Session, assignment: models.Assignment) -> None:
    if not settings.PUSH_NOTIFICATIONS_ENABLED:
        return

    recipients = _active_user_ids(db, exclude=assignment.creator_id)
    tokens = tokens_for_users(db, recipients, channel="assignments")

    parts = [assignment.title]
    if assignment.course:
        parts.append(assignment.course)
    body = " · ".join(part for part in parts if part)

    if tokens:
        dispatch_push(
            tokens,
            ASSIGNMENT_TITLE,
            body,
            {
                "type": "assignment",
                "assignment_id": assignment.id,
                "room": f"assignment:{assignment.id}",
            },
            channel_id="assignments",
        )
    _mark_initial_thresholds(db, assignment)


# ---------------------------------------------------------------------------
#  Approaching deadlines
# ---------------------------------------------------------------------------
def _deadline_body(assignment: models.Assignment, threshold: int, hours: float) -> str:
    if hours < 1:
        minutes = max(1, math.ceil(hours * 60))
        left = f"{minutes} دقیقه"
    else:
        left = f"{max(1, math.ceil(hours))} ساعت"
    course = f" · {assignment.course}" if assignment.course else ""
    return f"{assignment.title}{course} — {left} مانده"


def collect_deadline_jobs() -> list[dict[str, Any]]:
    """Reserve due reminders and return the pushes that should be sent.

    Runs in a worker thread. Each returned job is ``(tokens, title, body,
    data)``; sending happens on the event loop afterwards so the HTTP client is
    shared with the watcher instead of one thread per task.
    """
    now = datetime.utcnow()
    horizon = now + timedelta(hours=max(DEADLINE_THRESHOLDS))
    jobs: list[dict[str, Any]] = []

    with SessionLocal() as db:
        assignments = (
            db.query(models.Assignment)
            .filter(
                models.Assignment.deleted_at.is_(None),
                models.Assignment.due_date.isnot(None),
                models.Assignment.due_date > now,
                models.Assignment.due_date <= horizon,
            )
            .all()
        )

        for assignment in assignments:
            remaining_hours = (
                assignment.due_date - now
            ).total_seconds() / 3600
            # Pick the smallest threshold the task has entered. With a 10-minute
            # poll this fires once per threshold, and an assignment that enters
            # the window late still gets its 2-hour reminder.
            threshold = next(
                (
                    value
                    for value in sorted(DEADLINE_THRESHOLDS)
                    if remaining_hours <= value
                ),
                None,
            )
            if threshold is None:
                continue

            marker = models.DeadlineNotification(
                assignment_id=assignment.id, threshold_hours=threshold
            )
            db.add(marker)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                continue
            except Exception:  # pragma: no cover - never kill the watcher
                db.rollback()
                logger.warning(
                    "Could not reserve deadline marker assignment=%s",
                    assignment.id,
                    exc_info=True,
                )
                continue

            completed = {
                row[0]
                for row in db.query(models.AssignmentCompletion.user_id)
                .filter(models.AssignmentCompletion.assignment_id == assignment.id)
                .all()
            }
            pending = [
                user_id
                for user_id in _active_user_ids(db)
                if user_id not in completed
            ]
            tokens = tokens_for_users(db, pending, channel="deadlines")
            if not tokens:
                continue

            jobs.append(
                {
                    "tokens": tokens,
                    "title": DEADLINE_TITLE,
                    "body": _deadline_body(assignment, threshold, remaining_hours),
                    "data": {
                        "type": "assignment",
                        "assignment_id": assignment.id,
                        "room": f"assignment:{assignment.id}",
                        "threshold_hours": threshold,
                    },
                }
            )

    return jobs


async def deadline_watcher(interval_minutes: int) -> None:
    """Poll for deadlines until the app shuts down."""
    interval = max(60, int(interval_minutes * 60))
    # Let the slot finish booting and the database settle before the first pass.
    await asyncio.sleep(20)

    while True:
        try:
            jobs = await asyncio.to_thread(collect_deadline_jobs)
            for job in jobs:
                await send_push(
                    job["tokens"],
                    job["title"],
                    job["body"],
                    job["data"],
                    channel_id="deadlines",
                )
            if jobs:
                logger.info("Sent %d deadline reminder(s)", len(jobs))
        except asyncio.CancelledError:
            raise
        except Exception:  # pragma: no cover - the loop must survive anything
            logger.exception("Deadline watcher pass failed")

        await asyncio.sleep(interval)
