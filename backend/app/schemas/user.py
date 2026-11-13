from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import Text150


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: Text150
    account_type: Literal["attendee", "organizer"] = "attendee"


class UserOut(BaseModel):
    id: UUID
    email: EmailStr
    full_name: str
    role: Literal["attendee", "organizer", "admin"]
    is_active: bool
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int