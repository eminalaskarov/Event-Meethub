from uuid import UUID

import asyncpg
from fastapi import HTTPException, status

from app.schemas.user import UserOut


def can_manage_event(event: asyncpg.Record, user: UserOut | None) -> bool:
    return user is not None and (user.role == "admin" or event["organizer_id"] == user.id)


async def fetch_event_or_404(pool: asyncpg.Pool, event_id: UUID) -> asyncpg.Record:
    event = await pool.fetchrow(
        """
        SELECT id, organizer_id, venue_id, status, seating_mode, capacity
        FROM events
        WHERE id = $1
        """,
        event_id,
    )
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return event


async def fetch_visible_event(
    pool: asyncpg.Pool, event_id: UUID, user: UserOut | None
) -> asyncpg.Record:
    event = await fetch_event_or_404(pool, event_id)
    if event["status"] == "draft" and not can_manage_event(event, user):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return event


async def fetch_managed_event(
    pool: asyncpg.Pool, event_id: UUID, user: UserOut
) -> asyncpg.Record:
    event = await fetch_event_or_404(pool, event_id)
    if not can_manage_event(event, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not manage this event")
    return event


def require_draft(event: asyncpg.Record) -> None:
    if event["status"] != "draft":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This setup can only be changed while the event is a draft",
        )