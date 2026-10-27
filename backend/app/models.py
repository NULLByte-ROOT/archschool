from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import relationship
from datetime import datetime

from .database import Base

# RBAC roles. "owner" is a special account (server stats + code management),
# "admin" manages assignments/users and deletes any chat message, "friend"
# chats and comments but never manages assignments, "member" is read-only
# except completion toggles and assignment comments. The legacy "editor" role
# is retired; boot migrations convert those users to "admin".
ROLE_OWNER = "owner"
ROLE_ADMIN = "admin"
ROLE_FRIEND = "friend"
ROLE_MEMBER = "member"
VALID_ROLES = (ROLE_OWNER, ROLE_ADMIN, ROLE_FRIEND, ROLE_MEMBER)


def is_staff(user: "User") -> bool:
    """True for every role that may manage assignments, users and chat."""
    return bool(user.is_admin or user.role in (ROLE_ADMIN, ROLE_OWNER))


def is_owner(user: "User") -> bool:
    return user.role == ROLE_OWNER


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    code = Column(String(100), unique=True, nullable=False, index=True)
    password = Column(String(255), nullable=True)
    avatar_url = Column(String(500), nullable=True)
    bio = Column(Text, nullable=False, default="", server_default=text("''"))
    last_seen = Column(DateTime, nullable=True)
    is_admin = Column(Boolean, default=False)
    role = Column(
        String(20),
        nullable=False,
        default=ROLE_MEMBER,
        server_default=text("'member'"),
        index=True,
    )
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    assignments = relationship(
        "Assignment",
        foreign_keys="Assignment.owner_id",
        back_populates="owner",
    )
    created_assignments = relationship(
        "Assignment",
        foreign_keys="Assignment.creator_id",
        back_populates="creator",
    )
    completions = relationship(
        "AssignmentCompletion",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    sent_messages = relationship(
        "Message",
        foreign_keys="Message.sender_id",
        back_populates="sender",
        cascade="all, delete-orphan",
    )
    received_messages = relationship(
        "Message",
        foreign_keys="Message.receiver_id",
        back_populates="receiver",
    )
    attachments = relationship(
        "Attachment",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    push_tokens = relationship(
        "PushToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class SchoolSchedule(Base):
    """Admin-configurable school bell times (one row per period, 1..4).

    ``start_time`` / ``end_time`` are ``"HH:MM"`` strings in the school's local
    wall clock. Everything that computes school-time semantics — the current
    period, the "time left in the school day" deadline alignment — reads these
    instead of hard-coded 08:00-14:00 numbers.
    """

    __tablename__ = "school_schedule"

    id = Column(Integer, primary_key=True, index=True)
    period_number = Column(Integer, nullable=False, unique=True, index=True)
    start_time = Column(String(5), nullable=False)
    end_time = Column(String(5), nullable=False)


class Assignment(Base):
    __tablename__ = "assignments"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, default="")
    course = Column(String(100), default="", index=True)
    category = Column(String(20), default="")
    subtype = Column(String(40), default="")
    subject_id = Column(String(40), default="", index=True)
    due_date = Column(DateTime, nullable=True)
    completed = Column(Boolean, default=False, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    creator_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # Soft delete: the row (and every completion) stays in the database so
    # percentages, streaks and activity history never shrink. Lists filter it
    # out; analytics deliberately does not.
    deleted_at = Column(DateTime, nullable=True, index=True)

    owner = relationship(
        "User",
        foreign_keys=[owner_id],
        back_populates="assignments",
    )
    creator = relationship(
        "User",
        foreign_keys=[creator_id],
        back_populates="created_assignments",
    )
    completions = relationship(
        "AssignmentCompletion",
        back_populates="assignment",
        cascade="all, delete-orphan",
    )
    attachments = relationship(
        "Attachment",
        back_populates="assignment",
        cascade="all, delete-orphan",
    )
    messages = relationship(
        "Message",
        back_populates="assignment",
        cascade="all, delete-orphan",
        foreign_keys="Message.assignment_id",
    )


class AssignmentCompletion(Base):
    """Per-user completion of a shared assignment.

    Assignments are public in the team workspace, so ``Assignment.completed``
    alone cannot express who has finished the work. Each row here means one
    user has marked one assignment as done.
    """

    __tablename__ = "assignment_completions"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "assignment_id", name="uq_completion_user_assignment"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    assignment_id = Column(
        Integer,
        ForeignKey("assignments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    completed_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="completions")
    assignment = relationship("Assignment", back_populates="completions")


class DailyActivity(Base):
    """Historical "did this user do anything that school day" ledger.

    Streaks used to be derived from ``assignment_completions`` alone, so
    deleting an assignment (which cascades its completions away) could shorten
    or reset somebody's streak. This table is the delete-safe history: a row is
    written when a user marks an assignment done, decremented only when that
    same user un-marks it, and **never** touched when an assignment is deleted.
    The day is the school-local date (``SCHOOL_UTC_OFFSET_HOURS``).
    """

    __tablename__ = "daily_activity"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "activity_date", name="uq_daily_activity_user_date"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    activity_date = Column(Date, nullable=False, index=True)
    completions = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class CompletionToggleGuard(Base):
    """Anti-abuse bookkeeping for the "Done / Read" toggle.

    One row per (user, assignment) pair. Every toggle increments
    ``attempt_count`` inside the current one-hour window; the fourth attempt
    (``TOGGLE_LIMIT_PER_HOUR`` + 1) writes ``locked_until = now + lock`` and the
    API answers 429 until that timestamp passes. Rows are cheap and self-heal:
    once the window has elapsed the next attempt simply resets the counter.
    """

    __tablename__ = "completion_toggle_guards"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "assignment_id", name="uq_toggle_guard_user_assignment"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    assignment_id = Column(
        Integer,
        ForeignKey("assignments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    window_started_at = Column(DateTime, nullable=True)
    attempt_count = Column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    locked_until = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    sender_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    receiver_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    assignment_id = Column(
        Integer,
        ForeignKey("assignments.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    content = Column(Text, default="", nullable=False)
    file_url = Column(String(500), nullable=True)
    reply_to_id = Column(
        Integer,
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_pinned = Column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    edited_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    reply_to = relationship("Message", remote_side=[id], foreign_keys=[reply_to_id])
    sender = relationship(
        "User",
        foreign_keys=[sender_id],
        back_populates="sent_messages",
    )
    receiver = relationship(
        "User",
        foreign_keys=[receiver_id],
        back_populates="received_messages",
    )
    assignment = relationship(
        "Assignment",
        back_populates="messages",
        foreign_keys=[assignment_id],
    )
    reads = relationship(
        "MessageRead",
        back_populates="message",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="MessageRead.id",
    )

    @property
    def sender_username(self) -> str | None:
        return self.sender.username if self.sender else None

    @property
    def sender_avatar_url(self) -> str | None:
        return self.sender.avatar_url if self.sender else None

    @property
    def assignment_title(self) -> str | None:
        return self.assignment.title if self.assignment else None

    @property
    def seen_by(self) -> list[dict]:
        """Everyone except the sender who opened this message, with timestamps.

        Exposed as ``MessageOut.seen_by`` so a single tick becomes a double tick
        on the sender's screen; the sender is never part of their own receipt.
        """
        return [
            {"username": read.username, "read_at": read.read_at}
            for read in self.reads
            if read.user_id != self.sender_id and read.username
        ]


class MessageRead(Base):
    """One "this user has seen this message" row.

    A join table (instead of ``read_by`` on the message) is the only shape that
    can express a group chat: ten people each need their own timestamp. The
    unique pair makes the write idempotent, so opening a room twice is free.
    """

    __tablename__ = "message_reads"
    __table_args__ = (
        UniqueConstraint(
            "message_id", "user_id", name="uq_message_read_message_user"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(
        Integer,
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    read_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    message = relationship("Message", back_populates="reads")
    # `joined` keeps `MessageOut.seen_by` from issuing one query per receipt.
    user = relationship("User", lazy="joined")

    @property
    def username(self) -> str | None:
        return self.user.username if self.user else None


class ChatReadState(Base):
    """Per-user bookmark of when a chat room was last read.

    Rooms follow the same key layout as the WebSocket rooms:
    ``global``, ``dm:<low>:<high>`` and ``assignment:<id>``. Unread count for a
    room is every message in it with ``created_at > last_read_at`` that was not
    written by the reader.
    """

    __tablename__ = "chat_read_states"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    room = Column(String(80), nullable=False, index=True)
    last_read_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "room", name="uq_chat_read_user_room"),
    )


class Attachment(Base):
    __tablename__ = "attachments"
    id = Column(Integer, primary_key=True, index=True)
    assignment_id = Column(
        Integer,
        ForeignKey("assignments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_url = Column(String(500), nullable=False)
    file_name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    assignment = relationship("Assignment", back_populates="attachments")
    user = relationship("User", back_populates="attachments")

    @property
    def user_username(self) -> str | None:
        return self.user.username if self.user else None

    @property
    def uploader(self) -> "User | None":
        return self.user


class PushToken(Base):
    """One Expo push token registered by a mobile install.

    ``token`` is unique across the table: a phone that logs into a different
    account must move to that account instead of keeping a stale duplicate, and
    a token Expo reports as ``DeviceNotRegistered`` is deleted outright.
    """

    __tablename__ = "push_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token = Column(String(255), nullable=False, unique=True, index=True)
    device_type = Column(
        String(20), nullable=False, default="unknown", server_default=text("'unknown'")
    )
    # Per-device notification switches from the mobile Settings page. Stored
    # here (not only in AsyncStorage) so the sender filters the audience before
    # a push is ever dispatched, and so a reinstall restores the choices.
    notify_chat = Column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    notify_assignments = Column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    notify_deadlines = Column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    user = relationship("User", back_populates="push_tokens")


class DeadlineNotification(Base):
    """Idempotency marker for approaching-deadline pushes.

    The blue-green deploy runs two API instances against one database for a
    short window. The unique constraint makes the scheduler safe there: the
    second instance loses the insert race and stays silent. It also means a
    restart cannot re-send a reminder that already went out.
    """

    __tablename__ = "deadline_notifications"
    __table_args__ = (
        UniqueConstraint(
            "assignment_id",
            "threshold_hours",
            name="uq_deadline_notification_assignment_threshold",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    assignment_id = Column(
        Integer,
        ForeignKey("assignments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    threshold_hours = Column(Integer, nullable=False)
    sent_at = Column(DateTime, default=datetime.utcnow, nullable=False)
