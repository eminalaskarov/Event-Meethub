from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status

from app.access import fetch_event_or_404, fetch_managed_event
from app.dependencies import CurrentUser, DbPool, OrganizerUser
from app.qr_security import decrypt_ticket_qr, encrypt_ticket_qr
from app.schemas.ticket import (
    ScanOut,
    ScannerEventOut,
    ScanRequest,
    StaffAddRequest,
    StaffOut,
    TicketQrOut,
    WalletTicketOut,
)

router = APIRouter(tags=["tickets and scanning"])

TICKET_DETAIL_RESULTS = {"accepted", "already_used", "cancelled"}

@router.get("/tickets/mine", response_model=list[WalletTicketOut])
async def list_my_tickets(pool: DbPool, user: CurrentUser):
    rows = await pool.fetch(
        """
        SELECT
            t.id AS ticket_id, t.event_id, e.title AS event_title, e.starts_at,
            v.name AS venue_name, v.city, tt.name AS tier_name,
            s.section, s.row_label, s.seat_number,
            t.price_cents, e.currency, t.status, t.checked_in_at
        FROM tickets AS t
        JOIN events AS e ON e.id = t.event_id
        JOIN venues AS v ON v.id = e.venue_id
        JOIN ticket_tiers AS tt ON tt.id = t.tier_id
        LEFT JOIN event_seats AS es ON es.id = t.event_seat_id
        LEFT JOIN seats AS s ON s.id = es.seat_id
        WHERE t.owner_id = $1
        ORDER BY e.starts_at, s.section, s.row_label, s.seat_number, t.id
        LIMIT 200
        """,
        user.id,
    )
    return [dict(row) for row in rows]


@router.get("/tickets/scanner-events", response_model=list[ScannerEventOut])
async def list_scanner_events(pool: DbPool, user: CurrentUser):
    rows = await pool.fetch(
        """
        SELECT e.id, e.title, e.starts_at, v.name AS venue_name
        FROM events AS e
        JOIN venues AS v ON v.id = e.venue_id
        WHERE e.status = 'published'
          AND e.ends_at >= now() - INTERVAL '1 day'
          AND (
              $2::boolean
              OR e.organizer_id = $1
              OR EXISTS (
                  SELECT 1 FROM event_staff AS s
                  WHERE s.event_id = e.id AND s.user_id = $1
              )
          )
        ORDER BY e.starts_at, e.id
        LIMIT 100
        """,
        user.id,
        user.role == "admin",
    )
    return [dict(row) for row in rows]

@router.get("/tickets/{ticket_id}/qr", response_model=TicketQrOut)
async def get_ticket_qr(
    ticket_id: UUID,
    response: Response,
    pool: DbPool,
    user: CurrentUser,
):
    ticket = await pool.fetchrow(
        """
        SELECT id, event_id, status, qr_nonce, qr_key_version
        FROM tickets
        WHERE id = $1 AND owner_id = $2
        """,
        ticket_id,
        user.id,
    )
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    if ticket["status"] == "cancelled":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cancelled tickets do not have a usable QR code",
        )

    response.headers["Cache-Control"] = "no-store"
    return {
        "ticket_id": ticket["id"],
        "event_id": ticket["event_id"],
        "status": ticket["status"],
        "qr_payload": encrypt_ticket_qr(
            ticket["id"],
            ticket["qr_nonce"],
            ticket["qr_key_version"],
        ),
    }


@router.post("/events/{event_id}/scan", response_model=ScanOut)
async def scan_ticket(
    event_id: UUID,
    payload: ScanRequest,
    pool: DbPool,
    user: CurrentUser,
):
    """Business outcomes return HTTP 200. Unauthorized scanners are logged and get 403."""
    await fetch_event_or_404(pool, event_id)

    # An undecryptable QR passes NULL, which check_in_ticket records as invalid.
    ticket_id = decrypt_ticket_qr(payload.qr_payload)
    result = await pool.fetchval(
        "SELECT check_in_ticket($1::uuid, $2::uuid, $3::uuid)",
        ticket_id,
        event_id,
        user.id,
    )

    if result == "unauthorized":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to scan tickets for this event",
        )

    ticket = None
    if result in TICKET_DETAIL_RESULTS:
        row = await pool.fetchrow(
            """
            SELECT
                t.id AS ticket_id,
                u.full_name AS holder_name,
                tt.name AS tier_name,
                s.section,
                s.row_label,
                s.seat_number,
                t.status,
                t.checked_in_at
            FROM tickets AS t
            JOIN users AS u ON u.id = t.owner_id
            JOIN ticket_tiers AS tt ON tt.id = t.tier_id
            LEFT JOIN event_seats AS es ON es.id = t.event_seat_id
            LEFT JOIN seats AS s ON s.id = es.seat_id
            WHERE t.id = $1
            """,
            ticket_id,
        )
        ticket = dict(row) if row else None

    return {
        "result": result,
        "admitted": result == "accepted",
        "scanned_at": datetime.now(UTC),
        "ticket": ticket,
    }


@router.get("/events/{event_id}/staff", response_model=list[StaffOut])
async def list_event_staff(event_id: UUID, pool: DbPool, user: OrganizerUser):
    await fetch_managed_event(pool, event_id, user)
    rows = await pool.fetch(
        """
        SELECT u.id AS user_id, u.email::text AS email, u.full_name
        FROM event_staff AS s
        JOIN users AS u ON u.id = s.user_id
        WHERE s.event_id = $1
        ORDER BY u.full_name, u.id
        """,
        event_id,
    )
    return [dict(row) for row in rows]


@router.post("/events/{event_id}/staff", response_model=StaffOut, status_code=status.HTTP_201_CREATED)
async def add_event_staff(
    event_id: UUID,
    payload: StaffAddRequest,
    pool: DbPool,
    user: OrganizerUser,
):
    await fetch_managed_event(pool, event_id, user)
    staff_user = await pool.fetchrow(
        """
        SELECT id AS user_id, email::text AS email, full_name
        FROM users
        WHERE email = $1::text::citext AND is_active
        """,
        payload.email,
    )
    if staff_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    await pool.execute(
        """
        INSERT INTO event_staff (event_id, user_id)
        VALUES ($1, $2)
        ON CONFLICT DO NOTHING
        """,
        event_id,
        staff_user["user_id"],
    )
    return dict(staff_user)


@router.delete("/events/{event_id}/staff/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_event_staff(event_id: UUID, user_id: UUID, pool: DbPool, user: OrganizerUser):
    await fetch_managed_event(pool, event_id, user)
    result = await pool.execute(
        "DELETE FROM event_staff WHERE event_id = $1 AND user_id = $2",
        event_id,
        user_id,
    )
    if result == "DELETE 0":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Staff member not found")