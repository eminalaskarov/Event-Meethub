from datetime import UTC, datetime
from typing import Annotated, ClassVar, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.schemas.common import HttpUrlString, PatchModel, Text200

SeatingMode = Literal["reserved", "general"]
EventStatus = Literal["draft", "published", "cancelled", "completed"]
Currency = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]
CategoryId = Annotated[int, Field(ge=1, le=32767)]
Capacity = Annotated[int, Field(gt=0, le=2_147_483_647)]
TicketLimit = Annotated[int, Field(gt=0, le=50)]


class EventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    venue_id: UUID
    category_id: CategoryId | None = None
    title: Text200
    description: str | None = Field(default=None, max_length=10_000)
    cover_image_url: HttpUrlString | None = None
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    seating_mode: SeatingMode = "reserved"
    capacity: Capacity | None = None
    currency: Currency = "USD"
    max_tickets_per_order: TicketLimit = 6

    @model_validator(mode="after")
    def validate_event(self):
        if self.starts_at <= datetime.now(UTC):
            raise ValueError("starts_at must be in the future")
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        if self.seating_mode == "general" and self.capacity is None:
            raise ValueError("capacity is required for general admission")
        return self


class EventUpdate(PatchModel):
    nullable_fields: ClassVar[frozenset[str]] = frozenset(
        {"category_id", "description", "cover_image_url", "capacity"}
    )

    venue_id: UUID | None = None
    category_id: CategoryId | None = None
    title: Text200 | None = None
    description: str | None = Field(default=None, max_length=10_000)
    cover_image_url: HttpUrlString | None = None
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None
    seating_mode: SeatingMode | None = None
    capacity: Capacity | None = None
    currency: Currency | None = None
    max_tickets_per_order: TicketLimit | None = None


class EventOut(BaseModel):
    id: UUID
    organizer_id: UUID
    venue_id: UUID
    category_id: int | None
    title: str
    description: str | None
    cover_image_url: str | None
    starts_at: datetime
    ends_at: datetime
    status: EventStatus
    seating_mode: SeatingMode
    capacity: int | None
    currency: str
    max_tickets_per_order: int
    created_at: datetime
    updated_at: datetime
    venue_name: str
    venue_address: str
    city: str
    country: str
    latitude: float
    longitude: float
    distance_m: float | None = None