from datetime import datetime
from typing import ClassVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import PatchModel, Text100, Text200

Latitude = Field(ge=-90, le=90)
Longitude = Field(ge=-180, le=180)


class VenueCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Text200
    address: str = Field(min_length=1, max_length=500)
    city: Text100
    country: Text100
    latitude: float = Latitude
    longitude: float = Longitude
    google_place_id: str | None = Field(default=None, max_length=255)


class VenueUpdate(PatchModel):
    nullable_fields: ClassVar[frozenset[str]] = frozenset({"google_place_id"})

    name: Text200 | None = None
    address: str | None = Field(default=None, min_length=1, max_length=500)
    city: Text100 | None = None
    country: Text100 | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    google_place_id: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def coordinates_together(self):
        if ("latitude" in self.model_fields_set) != ("longitude" in self.model_fields_set):
            raise ValueError("latitude and longitude must be updated together")
        return self


class VenueOut(BaseModel):
    id: UUID
    name: str
    address: str
    city: str
    country: str
    latitude: float
    longitude: float
    google_place_id: str | None
    created_by: UUID
    created_at: datetime
    updated_at: datetime

class VenueNearbyOut(VenueOut):
    distance_m: float