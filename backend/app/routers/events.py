from typing import Any
from uuid import UUID

import asyncpg
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import AwareDatetime

from app.database import build_assignments
from app.dependencies import DbPool, OptionalUser, OrganizerUser
from app.schemas.event import EventCreate, EventOut, EventUpdate
from app.schemas.user import UserOut

router = APIRouter(prefix="/events", tags=["events"])

STRUCTURAL_FIELDS = {"venue_id", "seating_mode", "capacity", "currency"}


def _select_events(distance_sql: str = "NULL::double precision") -> str:
    return f"""
        SELECT
            e.id, e.organizer_id, e.venue_id, e.category_id, e.title, e.description,
            e.cover_image_url, e.starts_at, e.ends_at, e.status, e.seating_mode,
            e.capacity, e.currency, e.max_tickets_per_order, e.created_at, e.updated_at,
            v.name AS venue_name,
            v.address AS venue_address,
            v.city,
            v.country,
            ST_Y(v.location::geometry) AS latitude,
            ST_X(v.location::geometry) AS longitude,
            {distance_sql} AS distance_m
        FROM events AS e
        JOIN venues AS v ON v.id = e.venue_id
    """


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")


def _can_manage(event: asyncpg.Record, user: UserOut | None) -> bool:
    return user is not None and (user.role == "admin" or event["organizer_id"] == user.id)


async def _fetch_event(pool: asyncpg.Pool, event_id: UUID) -> asyncpg.Record | None:
    return await pool.fetchrow(f"{_select_events()} WHERE e.id = $1", event_id)


async def _fetch_managed_event(
    pool: asyncpg.Pool, event_id: UUID, user: UserOut
) -> asyncpg.Record:
    event = await _fetch_event(pool, event_id)
    if event is None:
        raise _not_found()
    if not _can_manage(event, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not manage this event")
    return event


@router.get("", response_model=list[EventOut])
async def list_events(
    pool: DbPool,
    lat: float | None = Query(default=None, ge=-90, le=90),
    lng: float | None = Query(default=None, ge=-180, le=180),
    radius_km: float = Query(default=25, gt=0, le=200),
    city: str | None = Query(default=None, max_length=100),
    category_id: int | None = Query(default=None, ge=1, le=32767),
    q: str | None = Query(default=None, max_length=100),
    starts_after: AwareDatetime | None = None,
    starts_before: AwareDatetime | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    if (lat is None) != (lng is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="lat and lng must be provided together",
        )

    params: list[Any] = []

    def bind(value: Any) -> str:
        params.append(value)
        return f"${len(params)}"

    where = ["e.status = 'published'", "e.ends_at >= now()"]
    distance_sql = "NULL::double precision"
    order_by = "e.starts_at ASC, e.id ASC"

    if lat is not None and lng is not None:
        point = (
            "ST_SetSRID(ST_MakePoint("
            f"{bind(lng)}::double precision, {bind(lat)}::double precision"
            "), 4326)::geography"
        )
        radius = bind(radius_km * 1000)
        where.append(f"ST_DWithin(v.location, {point}, {radius}::double precision)")
        distance_sql = f"ST_Distance(v.location, {point})"
        order_by = "distance_m ASC, e.starts_at ASC, e.id ASC"

    if city is not None:
        where.append(f"lower(v.city) = lower({bind(city)}::text)")
    if category_id is not None:
        where.append(f"e.category_id = {bind(category_id)}::smallint")
    if q:
        where.append(f"position(lower({bind(q)}::text) in lower(e.title)) > 0")
    if starts_after is not None:
        where.append(f"e.starts_at >= {bind(starts_after)}::timestamptz")
    if starts_before is not None:
        where.append(f"e.starts_at <= {bind(starts_before)}::timestamptz")

    limit_param = bind(limit)
    offset_param = bind(offset)

    rows = await pool.fetch(
        f"""
        {_select_events(distance_sql)}
        WHERE {" AND ".join(where)}
        ORDER BY {order_by}
        LIMIT {limit_param} OFFSET {offset_param}
        """,
        *params,
    )
    return [dict(row) for row in rows]

@router.get("/nearby", response_model=list[EventOut])
async def nearby_events(
    pool: DbPool,
    lat: float = Query(ge=-90, le=90),
    lng: float = Query(ge=-180, le=180),
    radius_km: float = Query(default=10, gt=0, le=200),
    category_id: int | None = Query(default=None, ge=1, le=32767),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    return await list_events(
        pool=pool,
        lat=lat,
        lng=lng,
        radius_km=radius_km,
        city=None,
        category_id=category_id,
        q=None,
        starts_after=None,
        starts_before=None,
        limit=limit,
        offset=offset,
    )

@router.get("/mine", response_model=list[EventOut])
async def list_my_events(
    pool: DbPool,
    user: OrganizerUser,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    rows = await pool.fetch(
        f"""
        {_select_events()}
        WHERE e.organizer_id = $1
        ORDER BY e.starts_at DESC, e.id
        LIMIT $2 OFFSET $3
        """,
        user.id,
        limit,
        offset,
    )
    return [dict(row) for row in rows]


@router.get("/{event_id}", response_model=EventOut)
async def get_event(event_id: UUID, pool: DbPool, user: OptionalUser):
    event = await _fetch_event(pool, event_id)
    if event is None or (event["status"] == "draft" and not _can_manage(event, user)):
        raise _not_found()
    return dict(event)


@router.post("", response_model=EventOut, status_code=status.HTTP_201_CREATED)
async def create_event(payload: EventCreate, pool: DbPool, user: OrganizerUser):
    try:
        event_id = await pool.fetchval(
            """
            INSERT INTO events (
                organizer_id, venue_id, category_id, title, description, cover_image_url,
                starts_at, ends_at, seating_mode, capacity, currency, max_tickets_per_order
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::seating_mode, $10, $11, $12)
            RETURNING id
            """,
            user.id,
            payload.venue_id,
            payload.category_id,
            payload.title,
            payload.description,
            payload.cover_image_url,
            payload.starts_at,
            payload.ends_at,
            payload.seating_mode,
            payload.capacity,
            payload.currency,
            payload.max_tickets_per_order,
        )
    except asyncpg.ForeignKeyViolationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Venue or category does not exist",
        ) from exc

    return dict(await _fetch_event(pool, event_id))


@router.patch("/{event_id}", response_model=EventOut)
async def update_event(event_id: UUID, payload: EventUpdate, pool: DbPool, user: OrganizerUser):
    event = await _fetch_managed_event(pool, event_id, user)
    values = payload.model_dump(exclude_unset=True)

    if event["status"] in {"cancelled", "completed"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This event can no longer be edited")

    if event["status"] == "published" and STRUCTURAL_FIELDS.intersection(values):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Venue, seating mode, capacity and currency cannot change after publishing",
        )

    assignments, params = build_assignments(values)
    params.extend([event_id, event["status"]])

    try:
        result = await pool.execute(
            f"""
            UPDATE events
            SET {", ".join(assignments)}
            WHERE id = ${len(params) - 1}
              AND status = ${len(params)}::event_status
            """,
            *params,
        )
    except asyncpg.ForeignKeyViolationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Venue or category is invalid for this event",
        ) from exc
    except asyncpg.CheckViolationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Dates, seating mode, or capacity are inconsistent",
        ) from exc

    if result == "UPDATE 0":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Event changed; please retry")

    return dict(await _fetch_event(pool, event_id))


@router.post("/{event_id}/publish", response_model=EventOut)
async def publish_event(event_id: UUID, pool: DbPool, user: OrganizerUser):
    event = await _fetch_managed_event(pool, event_id, user)

    if event["seating_mode"] == "reserved":
        ready = await pool.fetchval(
            "SELECT EXISTS (SELECT 1 FROM event_seats WHERE event_id = $1)", event_id
        )
        requirement = "Assign seats to ticket tiers before publishing"
    else:
        ready = await pool.fetchval(
            "SELECT EXISTS (SELECT 1 FROM ticket_tiers WHERE event_id = $1)", event_id
        )
        requirement = "Create at least one ticket tier before publishing"

    if not ready:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=requirement)

    result = await pool.execute(
        """
        UPDATE events
        SET status = 'published'
        WHERE id = $1 AND status = 'draft' AND starts_at > now()
        """,
        event_id,
    )
    if result == "UPDATE 0":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only upcoming draft events can be published",
        )
    return dict(await _fetch_event(pool, event_id))


@router.post("/{event_id}/cancel", response_model=EventOut)
async def cancel_event(event_id: UUID, pool: DbPool, user: OrganizerUser):
    await _fetch_managed_event(pool, event_id, user)
    result = await pool.execute(
        """
        UPDATE events
        SET status = 'cancelled'
        WHERE id = $1 AND status IN ('draft', 'published')
        """,
        event_id,
    )
    if result == "UPDATE 0":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only draft or published events can be cancelled",
        )
    return dict(await _fetch_event(pool, event_id))