from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

GooglePlaceId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,255}$")]
SessionToken = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,36}$")]


class PlaceSuggestionOut(BaseModel):
    google_place_id: str
    description: str
    main_text: str
    secondary_text: str


class PlaceDetailsOut(BaseModel):
    google_place_id: str
    name: str
    address: str
    city: str | None
    country: str | None
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class GooglePlaceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    google_place_id: GooglePlaceId
    session_token: SessionToken | None = None