from uuid import UUID

import asyncpg
from fastapi import APIRouter, HTTPException, status

from app.access import fetch_managed_event, fetch_visible_event, require_draft
from app.database import build_assignments
from app.dependencies import DbPool, OptionalUser, OrganizerUser
from app.schemas.booking import (
    BulkSeatCreate,
    CountOut,
    SeatAssignRequest,
    TierCreate,
    TierOut,
    TierUpdate,
    VenueSeatOut,
)
from app.schemas.user import UserOut

router = APIRouter(tags=["seat setup"])


async def _require_venue_manager(pool: asyncpg.Pool, venue_id: UUID, user: UserOut) -> None:
    owner_id = await pool.fetchval("SELECT created_by FROM venues WHERE id = $1", venue_id)
    if owner_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Venue not found")
    if user.role != "admin" and owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not own this venue")


@router.get("/venues/{venue_id}/seats", response_model=list[VenueSeatOut])
async def list_venue_seats(venue_id: UUID, pool: DbPool):
    rows = await pool.fetch(
        """
        SELECT id, venue_id, section, row_label, seat_number,
               pos_x::double precision AS pos_x,
               pos_y::double precision AS pos_y
        FROM seats
        WHERE venue_id = $1
        ORDER BY section, row_label, seat_number
        """,
        venue_id,
    )
    return [dict(row) for row in rows]


@router.post(
    "/venues/{venue_id}/seats/bulk",
    response_model=CountOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_venue_seats(
    venue_id: UUID, payload: BulkSeatCreate, pool: DbPool, user: OrganizerUser
):
    await _require_venue_manager(pool, venue_id, user)

    sections: list[str] = []
    rows: list[str] = []
    numbers: list[int] = []
    x_positions: list[float] = []
    y_positions: list[float] = []

    for block in payload.blocks:
        for row_index, row_label in enumerate(block.row_labels):
            for seat_index in range(block.seats_per_row):
                sections.append(block.section)
                rows.append(row_label)
                numbers.append(block.start_number + seat_index)
                x_positions.append(block.origin_x + seat_index * block.spacing_x)
                y_positions.append(block.origin_y + row_index * block.spacing_y)

    try:
        result = await pool.execute(
            """
            INSERT INTO seats (venue_id, section, row_label, seat_number, pos_x, pos_y)
            SELECT $1::uuid, section, row_label, seat_number, pos_x, pos_y
            FROM unnest(
                $2::text[], $3::text[], $4::integer[],
                $5::double precision[], $6::double precision[]
            ) AS layout(section, row_label, seat_number, pos_x, pos_y)
            """,
            venue_id,
            sections,
            rows,
            numbers,
            x_positions,
            y_positions,
        )
    except asyncpg.UniqueViolationError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="One or more seats already exist in this venue",
        ) from exc

    return {"count": int(result.split()[-1])}


@router.delete("/venues/{venue_id}/seats", response_model=CountOut)
async def delete_venue_seats(venue_id: UUID, pool: DbPool, user: OrganizerUser):
    await _require_venue_manager(pool, venue_id, user)
    try:
        result = await pool.execute("DELETE FROM seats WHERE venue_id = $1", venue_id)
    except asyncpg.ForeignKeyViolationError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This layout is already assigned to an event",
        ) from exc
    return {"count": int(result.split()[-1])}


@router.get("/events/{event_id}/tiers", response_model=list[TierOut])
async def list_tiers(event_id: UUID, pool: DbPool, user: OptionalUser):
    await fetch_visible_event(pool, event_id, user)
    rows = await pool.fetch(
        """
        SELECT id, event_id, name, price_cents
        FROM ticket_tiers
        WHERE event_id = $1
        ORDER BY price_cents, name
        """,
        event_id,
    )
    return [dict(row) for row in rows]


def _tier_name_conflict() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="This event already has a tier with that name",
    )


@router.post(
    "/events/{event_id}/tiers",
    response_model=TierOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_tier(event_id: UUID, payload: TierCreate, pool: DbPool, user: OrganizerUser):
    require_draft(await fetch_managed_event(pool, event_id, user))
    try:
        row = await pool.fetchrow(
            """
            INSERT INTO ticket_tiers (event_id, name, price_cents)
            VALUES ($1, $2, $3)
            RETURNING id, event_id, name, price_cents
            """,
            event_id,
            payload.name,
            payload.price_cents,
        )
    except asyncpg.UniqueViolationError as exc:
        raise _tier_name_conflict() from exc
    return dict(row)


@router.patch("/events/{event_id}/tiers/{tier_id}", response_model=TierOut)
async def update_tier(
    event_id: UUID, tier_id: UUID, payload: TierUpdate, pool: DbPool, user: OrganizerUser
):
    require_draft(await fetch_managed_event(pool, event_id, user))
    assignments, params = build_assignments(payload.model_dump(exclude_unset=True))
    params.extend([tier_id, event_id])

    try:
        row = await pool.fetchrow(
            f"""
            UPDATE ticket_tiers
            SET {", ".join(assignments)}
            WHERE id = ${len(params) - 1} AND event_id = ${len(params)}
            RETURNING id, event_id, name, price_cents
            """,
            *params,
        )
    except asyncpg.UniqueViolationError as exc:
        raise _tier_name_conflict() from exc

    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket tier not found")
    return dict(row)


@router.delete("/events/{event_id}/tiers/{tier_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tier(event_id: UUID, tier_id: UUID, pool: DbPool, user: OrganizerUser):
    require_draft(await fetch_managed_event(pool, event_id, user))
    try:
        result = await pool.execute(
            "DELETE FROM ticket_tiers WHERE id = $1 AND event_id = $2",
            tier_id,
            event_id,
        )
    except asyncpg.ForeignKeyViolationError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This tier is assigned to seats",
        ) from exc

    if result == "DELETE 0":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket tier not found")


@router.post("/events/{event_id}/seats/assign", response_model=CountOut)
async def assign_event_seats(
    event_id: UUID, payload: SeatAssignRequest, pool: DbPool, user: OrganizerUser
):
    await fetch_managed_event(pool, event_id, user)
    assigned = 0

    try:
        async with pool.acquire() as connection:
            async with connection.transaction():
                # FOR SHARE prevents the event being published mid-assignment.
                event = await connection.fetchrow(
                    """
                    SELECT venue_id, status, seating_mode
                    FROM events
                    WHERE id = $1
                    FOR SHARE
                    """,
                    event_id,
                )
                if event is None:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
                require_draft(event)
                if event["seating_mode"] != "reserved":
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Seats can only be assigned to reserved-seating events",
                    )

                for assignment in payload.assignments:
                    result = await connection.execute(
                        """
                        INSERT INTO event_seats (event_id, venue_id, seat_id, tier_id)
                        SELECT $1::uuid, $2::uuid, s.id, $3::uuid
                        FROM seats AS s
                        WHERE s.venue_id = $2::uuid
                          AND ($4::text[] IS NULL OR s.section = ANY ($4::text[]))
                        ON CONFLICT (event_id, seat_id)
                        DO UPDATE SET tier_id = EXCLUDED.tier_id
                        """,
                        event_id,
                        event["venue_id"],
                        assignment.tier_id,
                        assignment.sections,
                    )
                    count = int(result.split()[-1])
                    if count == 0:
                        raise HTTPException(
                            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="An assignment did not match any venue seats",
                        )
                    assigned += count
    except asyncpg.ForeignKeyViolationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Ticket tier does not belong to this event",
        ) from exc

    return {"count": assigned}