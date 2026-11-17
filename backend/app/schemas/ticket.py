from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

ScanResult = Literal["accepted", "already_used", "cancelled", "wrong_event", "invalid"]


class TicketQrOut(BaseModel):
    ticket_id: UUID
    event_id: UUID
    status: Literal["valid", "used"]
    qr_payload: str


class ScanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    qr_payload: str = Field(min_length=1, max_length=512)


class ScannedTicketOut(BaseModel):
    ticket_id: UUID
    holder_name: str
    tier_name: str
    section: str | None
    row_label: str | None
    seat_number: int | None
    status: Literal["valid", "used", "cancelled"]
    checked_in_at: datetime | None


class ScanOut(BaseModel):
    result: ScanResult
    admitted: bool
    scanned_at: datetime
    ticket: ScannedTicketOut | None


class StaffAddRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr


class StaffOut(BaseModel):
    user_id: UUID
    email: EmailStr
    full_name: str

class WalletTicketOut(BaseModel):
    ticket_id: UUID
    event_id: UUID
    event_title: str
    starts_at: datetime
    venue_name: str
    city: str
    tier_name: str
    section: str | None
    row_label: str | None
    seat_number: int | None
    price_cents: int
    currency: str
    status: Literal["valid", "used", "cancelled"]
    checked_in_at: datetime | None


class ScannerEventOut(BaseModel):
    id: UUID
    title: str
    starts_at: datetime
    venue_name: str