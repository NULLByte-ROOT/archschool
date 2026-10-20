from sqlalchemy import (
    Boolean,
    Column,
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

# RBAC roles. "admin" manages everything, "editor" can manage every assignment,
# "member" can only manage the assignments they created.
ROLE_ADMIN = "admin"
ROLE_EDITOR = "editor"
ROLE_MEMBER = "member"
VALID_ROLES = (ROLE_ADMIN, ROLE_EDITOR, ROLE_MEMBER)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    code = Column(String(100), unique=True, nullable=False, index=True)
    is_admin = Column(Boolean, default=False)
    role = Column(
        String(20),
        nullable=False,
        default=ROLE_MEMBER,
        server_default=text("'member'"),
        index=True,
    )
    is_active = Column(Boolean, default=True)
    points = Column(Integer, nullable=False, default=0, server_default=text("0"))
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
    points_awarded = Column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    creator_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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

    @property
    def sender_username(self) -> str | None:
        return self.sender.username if self.sender else None


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
