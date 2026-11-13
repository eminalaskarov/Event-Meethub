from uuid import UUID

import asyncpg
from fastapi import APIRouter, HTTPException, Query, status

from app.database import build_assignments
from app.dependencies import DbPool, OrganizerUser
from app.schemas.venue import VenueCreate, VenueOut, VenueUpdate, VenueNearbyOut

router = APIRouter(prefix="/venues", tags=["venues"])

VENUE_COLUMNS = """
    id, name, address, city, country,
    ST_Y(location::geometry) AS latitude,
    ST_X(location::geometry) AS longitude,
    google_place_id, created_by, created_at, updated_at
"""


def _place_conflict(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="A venue with this Google Place ID already exists",
    )


@router.get("", response_model=list[VenueOut])
async def list_venues(
    pool: DbPool,
    city: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    rows = await pool.fetch(
        f"""
        SELECT {VENUE_COLUMNS}
        FROM venues
        WHERE ($1::text IS NULL OR lower(city) = lower($1::text))
        ORDER BY name, id
        LIMIT $2 OFFSET $3
        """,
        city,
        limit,
        offset,
    )
    return [dict(row) for row in rows]


@router.get("/{venue_id}", response_model=VenueOut)

@router.get("/nearby", response_model=list[VenueNearbyOut])
async def nearby_venues(
    pool: DbPool,
    lat: float = Query(ge=-90, le=90),
    lng: float = Query(ge=-180, le=180),
    radius_km: float = Query(default=10, gt=0, le=200),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    point = "ST_SetSRID(ST_MakePoint($1::double precision, $2::double precision), 4326)::geography"
    rows = await pool.fetch(
        f"""
        SELECT {VENUE_COLUMNS}, ST_Distance(location, {point}) AS distance_m
        FROM venues
        WHERE ST_DWithin(location, {point}, $3::double precision)
        ORDER BY distance_m ASC, id ASC
        LIMIT $4 OFFSET $5
        """,
        lng,
        lat,
        radius_km * 1000,
        limit,
        offset,
    )
    return [dict(row) for row in rows]

async def get_venue(venue_id: UUID, pool: DbPool):
    row = await pool.fetchrow(f"SELECT {VENUE_COLUMNS} FROM venues WHERE id = $1", venue_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Venue not found")
    return dict(row)


@router.post("", response_model=VenueOut, status_code=status.HTTP_201_CREATED)
async def create_venue(payload: VenueCreate, pool: DbPool, user: OrganizerUser):
    try:
        row = await pool.fetchrow(
            f"""
            INSERT INTO venues (
                name, address, city, country, location, google_place_id, created_by
            )
            VALUES (
                $1, $2, $3, $4,
                ST_SetSRID(ST_MakePoint($5::double precision, $6::double precision), 4326)::geography,
                $7, $8
            )
            RETURNING {VENUE_COLUMNS}
            """,
            payload.name,
            payload.address,
            payload.city,
            payload.country,
            payload.longitude,
            payload.latitude,
            payload.google_place_id,
            user.id,
        )
    except asyncpg.UniqueViolationError as exc:
        raise _place_conflict(exc) from exc
    return dict(row)


@router.patch("/{venue_id}", response_model=VenueOut)
async def update_venue(venue_id: UUID, payload: VenueUpdate, pool: DbPool, user: OrganizerUser):
    owner_id = await pool.fetchval("SELECT created_by FROM venues WHERE id = $1", venue_id)
    if owner_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Venue not found")
    if user.role != "admin" and owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not own this venue")

    values = payload.model_dump(exclude_unset=True)
    latitude = values.pop("latitude", None)
    longitude = values.pop("longitude", None)
    assignments, params = build_assignments(values)

    if latitude is not None:
        params.extend([longitude, latitude])
        assignments.append(
            "location = ST_SetSRID(ST_MakePoint("
            f"${len(params) - 1}::double precision, ${len(params)}::double precision"
            "), 4326)::geography"
        )

    params.append(venue_id)
    try:
        row = await pool.fetchrow(
            f"""
            UPDATE venues
            SET {", ".join(assignments)}
            WHERE id = ${len(params)}
            RETURNING {VENUE_COLUMNS}
            """,
            *params,
        )
    except asyncpg.UniqueViolationError as exc:
        raise _place_conflict(exc) from exc

    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Venue not found")
    return dict(row)