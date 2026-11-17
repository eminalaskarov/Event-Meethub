from datetime import datetime
from typing import Annotated, ClassVar, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.schemas.common import PatchModel, Text80

Section = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
RowLabel = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10)]
PriceCents = Annotated[int, Field(ge=0, le=10_000_000)]
SeatIds = Annotated[list[UUID], Field(min_length=1, max_length=50)]
MAX_SEATS_PER_REQUEST = 5000


class SeatBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section: Section
    row_labels: list[RowLabel] = Field(min_length=1, max_length=200)
    seats_per_row: int = Field(ge=1, le=500)
    start_number: int = Field(default=1, ge=1, le=10_000)
    origin_x: float = Field(default=0, ge=0, le=100_000)
    origin_y: float = Field(default=0, ge=0, le=100_000)
    spacing_x: float = Field(default=40, gt=0, le=500)
    spacing_y: float = Field(default=40, gt=0, le=500)


class BulkSeatCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    blocks: list[SeatBlock] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def validate_total(self):
        total = sum(len(block.row_labels) * block.seats_per_row for block in self.blocks)
        if total > MAX_SEATS_PER_REQUEST:
            raise ValueError(f"A request can create at most {MAX_SEATS_PER_REQUEST} seats")
        return self


class VenueSeatOut(BaseModel):
    id: UUID
    venue_id: UUID
    section: str
    row_label: str
    seat_number: int
    pos_x: float | None
    pos_y: float | None


class CountOut(BaseModel):
    count: int


class TierCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Text80
    price_cents: PriceCents


class TierUpdate(PatchModel):
    name: Text80 | None = None
    price_cents: PriceCents | None = None


class TierOut(BaseModel):
    id: UUID
    event_id: UUID
    name: str
    price_cents: int


class SeatAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tier_id: UUID
    sections: list[Section] | None = Field(default=None, min_length=1, max_length=100)


class SeatAssignRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assignments: list[SeatAssignment] = Field(min_length=1, max_length=50)


class LiveSeatOut(BaseModel):
    event_seat_id: UUID
    seat_id: UUID
    section: str
    row_label: str
    seat_number: int
    pos_x: float | None
    pos_y: float | None
    tier_id: UUID
    tier_name: str
    price_cents: int
    status: Literal["available", "held", "booked", "blocked"]
    held_by_me: bool
    hold_expires_at: datetime | None


class SeatMapOut(BaseModel):
    event_id: UUID
    seating_mode: Literal["reserved", "general"]
    capacity: int | None
    tickets_remaining: int
    server_time: datetime
    seats: list[LiveSeatOut]


class HoldRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_seat_ids: SeatIds


class HoldOut(BaseModel):
    event_id: UUID
    event_seat_ids: list[UUID]
    hold_expires_at: datetime


class ReleaseOut(BaseModel):
    event_id: UUID
    released_event_seat_ids: list[UUID]


class ConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_seat_ids: SeatIds


class GeneralBookingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tier_id: UUID
    quantity: int = Field(ge=1, le=50)


class TicketSummaryOut(BaseModel):
    id: UUID
    tier_id: UUID
    tier_name: str
    event_seat_id: UUID | None
    section: str | None
    row_label: str | None
    seat_number: int | None
    price_cents: int
    status: Literal["valid", "used", "cancelled"]


class OrderOut(BaseModel):
    id: UUID
    event_id: UUID
    status: Literal["confirmed", "cancelled", "refunded"]
    total_cents: int
    currency: str
    created_at: datetime
    tickets: list[TicketSummaryOut]