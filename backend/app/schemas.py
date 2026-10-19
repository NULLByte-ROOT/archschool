from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class UserBase(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)


class UserCreate(UserBase):
    code: Optional[str] = Field(None, min_length=6, max_length=6)
    is_admin: bool = False


class UserUpdate(BaseModel):
    username: Optional[str] = Field(None, min_length=2, max_length=50)
    code: Optional[str] = Field(None, min_length=6, max_length=6)
    is_active: Optional[bool] = None


class UserOut(UserBase):
    id: int
    is_admin: bool
    is_active: bool
    created_at: datetime
    code: Optional[str] = None

    model_config = {"from_attributes": True}


class LoginRequest(BaseModel):
    username: str
    code: str = Field(..., min_length=6, max_length=6)


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
    priority: int = Field(2, ge=1, le=3)


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
    priority: Optional[int] = Field(None, ge=1, le=3)


class AssignmentOut(AssignmentBase):
    id: int
    owner_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}