from typing import Annotated
from uuid import UUID

import asyncpg
from fastapi import APIRouter, HTTPException, Path, Query, Response, status

from app.dependencies import DbPool, HttpClient, OrganizerUser
from app.google_places import autocomplete_places, get_place_details
from app.routers.setup import _require_venue_manager
from app.routers.venues import VENUE_COLUMNS
from app.schemas.place import (
    GooglePlaceId,
    GooglePlaceRequest,
    PlaceDetailsOut,
    PlaceSuggestionOut,
    SessionToken,
)
from app.schemas.venue import VenueOut

router = APIRouter(prefix="/venues", tags=["google places"])

GEOGRAPHY_POINT = (
    "ST_SetSRID(ST_MakePoint({lng}::double precision, {lat}::double precision), 4326)::geography"
)


async def _venue_by_place_id(pool: asyncpg.Pool, place_id: str) -> asyncpg.Record | None:
    return await pool.fetchrow(
        f"SELECT {VENUE_COLUMNS} FROM venues WHERE google_place_id = $1",
        place_id,
    )


@router.get("/google/autocomplete", response_model=list[PlaceSuggestionOut])
async def autocomplete(
    client: HttpClient,
    user: OrganizerUser,
    input: str = Query(min_length=1, max_length=200),
    session_token: Annotated[SessionToken | None, Query()] = None,
    lat: float | None = Query(default=None, ge=-90, le=90),
    lng: float | None = Query(default=None, ge=-180, le=180),
):
    if (lat is None) != (lng is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="lat and lng must be provided together",
        )
    return await autocomplete_places(client, input, session_token, lat, lng)


@router.get("/google/places/{place_id}", response_model=PlaceDetailsOut)
async def place_details(
    place_id: Annotated[GooglePlaceId, Path()],
    client: HttpClient,
    user: OrganizerUser,
    session_token: Annotated[SessionToken | None, Query()] = None,
):
    return await get_place_details(client, place_id, session_token)


@router.post("/google/import", response_model=VenueOut, status_code=status.HTTP_201_CREATED)
async def import_google_venue(
    payload: GooglePlaceRequest,
    response: Response,
    pool: DbPool,
    client: HttpClient,
    user: OrganizerUser,
):
    """Create a venue from a Place ID, or return the venue already linked to it."""
    existing = await _venue_by_place_id(pool, payload.google_place_id)
    if existing is not None:
        response.status_code = status.HTTP_200_OK
        return dict(existing)

    details = await get_place_details(client, payload.google_place_id, payload.session_token)
    if not details["address"] or not details["city"] or not details["country"]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="This place is missing its address, city, or country",
        )

    point = GEOGRAPHY_POINT.format(lng="$5", lat="$6")
    try:
        row = await pool.fetchrow(
            f"""
            INSERT INTO venues (
                name, address, city, country, location, google_place_id, created_by
            )
            VALUES ($1, $2, $3, $4, {point}, $7, $8)
            RETURNING {VENUE_COLUMNS}
            """,
            details["name"],
            details["address"],
            details["city"],
            details["country"],
            details["longitude"],
            details["latitude"],
            details["google_place_id"],
            user.id,
        )
    except asyncpg.UniqueViolationError:
        # Another request imported it first, or Google returned a newer ID.
        existing = await _venue_by_place_id(pool, details["google_place_id"])
        if existing is None:
            raise
        response.status_code = status.HTTP_200_OK
        return dict(existing)

    return dict(row)


@router.post("/{venue_id}/google-place", response_model=VenueOut)
async def link_google_place(
    venue_id: UUID,
    payload: GooglePlaceRequest,
    pool: DbPool,
    client: HttpClient,
    user: OrganizerUser,
):
    """Verify a Place ID, then sync the venue's address and coordinates from it."""
    await _require_venue_manager(pool, venue_id, user)
    details = await get_place_details(client, payload.google_place_id, payload.session_token)

    if not details["address"]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="This place does not have an address",
        )

    point = GEOGRAPHY_POINT.format(lng="$3", lat="$4")
    try:
        row = await pool.fetchrow(
            f"""
            UPDATE venues
            SET google_place_id = $1, address = $2, location = {point}
            WHERE id = $5
            RETURNING {VENUE_COLUMNS}
            """,
            details["google_place_id"],
            details["address"],
            details["longitude"],
            details["latitude"],
            venue_id,
        )
    except asyncpg.UniqueViolationError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Another venue is already linked to this place",
        ) from exc

    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Venue not found")
    return dict(row)