from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class UserBase(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)


class UserCreate(UserBase):
    code: Optional[str] = Field(None, min_length=6, max_length=6)
    is_admin: bool = False
    role: Optional[str] = Field(None, max_length=20)


class UserUpdate(BaseModel):
    username: Optional[str] = Field(None, min_length=2, max_length=50)
    code: Optional[str] = Field(None, min_length=6, max_length=6)
    avatar_url: Optional[str] = Field(None, max_length=500)
    bio: Optional[str] = Field(None, max_length=500)
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None
    role: Optional[str] = Field(None, max_length=20)


class UserSelfUpdate(BaseModel):
    avatar_url: Optional[str] = Field(None, max_length=500)
    bio: Optional[str] = Field(None, max_length=500)


class UserOut(UserBase):
    id: int
    is_admin: bool
    role: str = "member"
    is_active: bool
    points: int = 0
    avatar_url: Optional[str] = None
    bio: str = ""
    last_seen: Optional[datetime] = None
    created_at: datetime
    code: Optional[str] = None

    model_config = {"from_attributes": True}


class UserProfileOut(BaseModel):
    id: int
    username: str
    is_admin: bool
    role: str = "member"
    points: int = 0
    avatar_url: Optional[str] = None
    bio: str = ""
    last_seen: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PublicUserOut(BaseModel):
    id: int
    username: str
    is_admin: bool
    role: str = "member"
    points: int = 0
    avatar_url: Optional[str] = None

    model_config = {"from_attributes": True}


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)
    code: str = Field(..., pattern=r"^[A-Z0-9]{6}$")


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)
    code: str = Field(..., pattern=r"^[A-Z0-9]{6}$")


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class AssignmentBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    course: str = ""
    category: str = ""
    subtype: str = ""
    subject_id: str = ""
    due_date: Optional[datetime] = None
    completed: bool = False


class AssignmentCreate(AssignmentBase):
    pass


class AssignmentUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    course: Optional[str] = None
    category: Optional[str] = None
    subtype: Optional[str] = None
    subject_id: Optional[str] = None
    due_date: Optional[datetime] = None
    completed: Optional[bool] = None


class CompletedByUser(BaseModel):
    id: int
    username: Optional[str] = None


class AssignmentOut(AssignmentBase):
    id: int
    owner_id: Optional[int] = None
    creator_id: Optional[int] = None
    creator_username: Optional[str] = None
    completed_by_users: list[CompletedByUser] = []
    is_completed_by_me: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ------------------------------------------------------------------
#  چت، پیوست‌ها و امتیازها
# ------------------------------------------------------------------
class MessageCreate(BaseModel):
    content: str = Field("", max_length=5000)
    receiver_id: Optional[int] = None
    assignment_id: Optional[int] = None
    file_url: Optional[str] = Field(None, max_length=500)
    reply_to_id: Optional[int] = None


class ReplyPreview(BaseModel):
    id: int
    sender_id: int
    sender_username: Optional[str] = None
    content: str = ""
    file_url: Optional[str] = None

    model_config = {"from_attributes": True}


class MessageOut(BaseModel):
    id: int
    sender_id: int
    sender_username: Optional[str] = None
    sender_avatar_url: Optional[str] = None
    receiver_id: Optional[int] = None
    assignment_id: Optional[int] = None
    assignment_title: Optional[str] = None
    content: str = ""
    file_url: Optional[str] = None
    reply_to: Optional[ReplyPreview] = None
    is_pinned: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class DirectPreview(BaseModel):
    peer_id: int
    message: MessageOut


class ChatOverview(BaseModel):
    global_message: Optional[MessageOut] = None
    directs: list[DirectPreview] = []


class UnreadRoom(BaseModel):
    room: str
    unread_count: int


class UnreadSummary(BaseModel):
    rooms: list[UnreadRoom] = []
    total: int = 0


class AttachmentOut(BaseModel):
    id: int
    assignment_id: int
    user_id: int
    user_username: Optional[str] = None
    uploader: Optional[PublicUserOut] = None
    file_url: str
    file_name: str
    created_at: datetime

    model_config = {"from_attributes": True}


class UploadOut(BaseModel):
    url: str
    file_name: str
    size: int


class TeamMemberOut(BaseModel):
    user: PublicUserOut
    completed: bool
    is_self: bool = False


# ------------------------------------------------------------------
#  برنامه‌ی زنگ‌های مدرسه (School bell times)
# ------------------------------------------------------------------
TIME_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"


class SchoolPeriodIn(BaseModel):
    period_number: int = Field(..., ge=1, le=4)
    start_time: str = Field(..., pattern=TIME_PATTERN, examples=["08:00"])
    end_time: str = Field(..., pattern=TIME_PATTERN, examples=["09:30"])


class SchoolScheduleOut(BaseModel):
    periods: list[SchoolPeriodIn]

    @property
    def school_start(self) -> str | None:
        return self.periods[0].start_time if self.periods else None

    @property
    def school_end(self) -> str | None:
        return self.periods[-1].end_time if self.periods else None


class SchoolScheduleUpdate(BaseModel):
    periods: list[SchoolPeriodIn] = Field(..., min_length=4, max_length=4)
