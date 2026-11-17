from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

import asyncpg
from fastapi import APIRouter, HTTPException, Query, status

from app.access import fetch_visible_event
from app.config import settings
from app.dependencies import CurrentUser, DbPool, OptionalUser, RealtimeHub
from app.schemas.booking import (
    ConfirmRequest,
    GeneralBookingRequest,
    HoldOut,
    HoldRequest,
    OrderOut,
    ReleaseOut,
    SeatMapOut,
)
from app.seat_realtime import SeatRealtimeHub, publish_seat_state, server_time

router = APIRouter(prefix="/events", tags=["booking"])

BOOKING_ERRORS = {
    "EH001": (status.HTTP_409_CONFLICT, "seat_unavailable"),
    "EH002": (status.HTTP_409_CONFLICT, "event_not_bookable"),
    "EH003": (status.HTTP_409_CONFLICT, "hold_missing_or_expired"),
    "EH005": (status.HTTP_422_UNPROCESSABLE_ENTITY, "ticket_limit_exceeded"),
    "EH007": (status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid_request"),
    "EH008": (status.HTTP_409_CONFLICT, "sold_out"),
}


@contextmanager
def translate_booking_errors() -> Iterator[None]:
    try:
        yield
    except asyncpg.PostgresError as exc:
        mapped = BOOKING_ERRORS.get(exc.sqlstate)
        if mapped is None:
            raise
        status_code, code = mapped
        raise HTTPException(
            status_code=status_code,
            detail={"code": code, "message": exc.message},
        ) from exc


async def _order_response(pool: asyncpg.Pool, order_id: UUID) -> dict:
    order = await pool.fetchrow(
        """
        SELECT id, event_id, status, total_cents, currency, created_at
        FROM orders
        WHERE id = $1
        """,
        order_id,
    )
    tickets = await pool.fetch(
        """
        SELECT t.id, t.tier_id, tt.name AS tier_name, t.event_seat_id,
               s.section, s.row_label, s.seat_number, t.price_cents, t.status
        FROM tickets AS t
        JOIN ticket_tiers AS tt ON tt.id = t.tier_id
        LEFT JOIN event_seats AS es ON es.id = t.event_seat_id
        LEFT JOIN seats AS s ON s.id = es.seat_id
        WHERE t.order_id = $1
        ORDER BY s.section, s.row_label, s.seat_number, t.id
        """,
        order_id,
    )
    return {**dict(order), "tickets": [dict(ticket) for ticket in tickets]}


async def _general_tickets_remaining(pool: asyncpg.Pool, event_id: UUID) -> int:
    return await pool.fetchval(
        """
        SELECT GREATEST(
            e.capacity - (
                SELECT count(*)
                FROM tickets AS t
                WHERE t.event_id = e.id AND t.status IN ('valid', 'used')
            ),
            0
        )::integer
        FROM events AS e
        WHERE e.id = $1
        """,
        event_id,
    )


async def _publish_general_availability(
    pool: asyncpg.Pool, hub: SeatRealtimeHub, event_id: UUID
) -> None:
    try:
        remaining = await _general_tickets_remaining(pool, event_id)
    except (asyncpg.PostgresError, asyncpg.InterfaceError, OSError):
        return

    await hub.publish(
        event_id,
        {
            "type": "availability.updated",
            "event_id": str(event_id),
            "tickets_remaining": remaining,
            "server_time": server_time(),
        },
    )


@router.get("/{event_id}/seats", response_model=SeatMapOut)
async def get_live_seats(event_id: UUID, pool: DbPool, user: OptionalUser):
    event = await fetch_visible_event(pool, event_id, user)

    if event["seating_mode"] == "general":
        return {
            "event_id": event_id,
            "seating_mode": "general",
            "capacity": event["capacity"],
            "tickets_remaining": await _general_tickets_remaining(pool, event_id),
            "server_time": datetime.now(UTC),
            "seats": [],
        }

    rows = await pool.fetch(
        """
        SELECT
            es.id AS event_seat_id,
            es.seat_id,
            s.section,
            s.row_label,
            s.seat_number,
            s.pos_x::double precision AS pos_x,
            s.pos_y::double precision AS pos_y,
            es.tier_id,
            t.name AS tier_name,
            t.price_cents,
            CASE
                WHEN es.status = 'held' AND es.hold_expires_at <= clock_timestamp()
                THEN 'available'::seat_status
                ELSE es.status
            END AS status,
            COALESCE(
                es.status = 'held'
                AND es.hold_expires_at > clock_timestamp()
                AND es.held_by = $2::uuid,
                FALSE
            ) AS held_by_me,
            CASE
                WHEN es.status = 'held' AND es.hold_expires_at > clock_timestamp()
                THEN es.hold_expires_at
            END AS hold_expires_at
        FROM event_seats AS es
        JOIN seats AS s ON s.id = es.seat_id
        JOIN ticket_tiers AS t ON t.id = es.tier_id
        WHERE es.event_id = $1
        ORDER BY s.section, s.row_label, s.seat_number
        """,
        event_id,
        user.id if user else None,
    )

    seats = [dict(row) for row in rows]
    return {
        "event_id": event_id,
        "seating_mode": "reserved",
        "capacity": event["capacity"],
        "tickets_remaining": sum(seat["status"] == "available" for seat in seats),
        "server_time": datetime.now(UTC),
        "seats": seats,
    }


@router.post("/{event_id}/holds", response_model=HoldOut)
async def hold_event_seats(
    event_id: UUID,
    payload: HoldRequest,
    pool: DbPool,
    hub: RealtimeHub,
    user: CurrentUser,
):
    seat_ids = list(dict.fromkeys(payload.event_seat_ids))

    with translate_booking_errors():
        expires_at = await pool.fetchval(
            "SELECT hold_seats($1::uuid, $2::uuid, $3::uuid[], $4::interval)",
            event_id,
            user.id,
            seat_ids,
            timedelta(seconds=settings.seat_hold_ttl_seconds),
        )

    await publish_seat_state(pool, hub, event_id, seat_ids, "held")
    return {
        "event_id": event_id,
        "event_seat_ids": seat_ids,
        "hold_expires_at": expires_at,
    }


@router.delete("/{event_id}/holds", response_model=ReleaseOut)
async def release_event_seats(
    event_id: UUID,
    pool: DbPool,
    hub: RealtimeHub,
    user: CurrentUser,
    event_seat_id: Annotated[list[UUID] | None, Query()] = None,
):
    """Release the listed seats, or all of the user's holds if none are listed."""
    if event_seat_id is not None and len(event_seat_id) > 50:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At most 50 seats can be released per request",
        )

    if event_seat_id is None:
        rows = await pool.fetch(
            """
            SELECT id
            FROM event_seats
            WHERE event_id = $1 AND status = 'held' AND held_by = $2
            """,
            event_id,
            user.id,
        )
        requested_ids = [row["id"] for row in rows]
    else:
        requested_ids = list(dict.fromkeys(event_seat_id))

    rows = await pool.fetch(
        """
        SELECT seat_id
        FROM release_seats($1::uuid, $2::uuid, $3::uuid[]) AS released(seat_id)
        """,
        event_id,
        user.id,
        requested_ids,
    )
    released_ids = [row["seat_id"] for row in rows]

    await publish_seat_state(pool, hub, event_id, released_ids, "released")
    return {"event_id": event_id, "released_event_seat_ids": released_ids}


@router.post("/{event_id}/confirm", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
async def confirm_event_booking(
    event_id: UUID,
    payload: ConfirmRequest,
    pool: DbPool,
    hub: RealtimeHub,
    user: CurrentUser,
):
    seat_ids = list(dict.fromkeys(payload.event_seat_ids))

    with translate_booking_errors():
        order_id = await pool.fetchval(
            "SELECT confirm_booking($1::uuid, $2::uuid, $3::uuid[])",
            event_id,
            user.id,
            seat_ids,
        )

    await publish_seat_state(pool, hub, event_id, seat_ids, "booked")
    return await _order_response(pool, order_id)


@router.post(
    "/{event_id}/book-general",
    response_model=OrderOut,
    status_code=status.HTTP_201_CREATED,
)
async def book_general_tickets(
    event_id: UUID,
    payload: GeneralBookingRequest,
    pool: DbPool,
    hub: RealtimeHub,
    user: CurrentUser,
):
    with translate_booking_errors():
        order_id = await pool.fetchval(
            "SELECT book_general_admission($1::uuid, $2::uuid, $3::uuid, $4::integer)",
            event_id,
            user.id,
            payload.tier_id,
            payload.quantity,
        )

    await _publish_general_availability(pool, hub, event_id)
    return await _order_response(pool, order_id)