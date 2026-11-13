BEGIN;

-- ===========================================================
-- Extensions
-- ===========================================================
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;  -- gen_random_bytes()
CREATE EXTENSION IF NOT EXISTS citext;    -- case-insensitive email

-- ===========================================================
-- Enum types
-- ===========================================================
CREATE TYPE user_role     AS ENUM ('attendee', 'organizer', 'admin');
CREATE TYPE event_status  AS ENUM ('draft', 'published', 'cancelled', 'completed');
CREATE TYPE seating_mode  AS ENUM ('reserved', 'general');
CREATE TYPE seat_status   AS ENUM ('available', 'held', 'booked', 'blocked');
CREATE TYPE order_status  AS ENUM ('confirmed', 'cancelled', 'refunded');
CREATE TYPE ticket_status AS ENUM ('valid', 'used', 'cancelled');
CREATE TYPE scan_result   AS ENUM (
    'accepted', 'already_used', 'cancelled',
    'wrong_event', 'invalid', 'unauthorized'
);

-- ===========================================================
-- Tables
-- ===========================================================
CREATE TABLE users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email         CITEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name     VARCHAR(150) NOT NULL,
    role          user_role NOT NULL DEFAULT 'attendee',
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE categories (
    id   SMALLINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name VARCHAR(80) NOT NULL UNIQUE
);

CREATE TABLE venues (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(200) NOT NULL,
    address         TEXT NOT NULL,
    city            VARCHAR(100) NOT NULL,
    country         VARCHAR(100) NOT NULL,
    location        GEOGRAPHY(Point, 4326) NOT NULL,  -- ST_MakePoint(lng, lat)
    google_place_id TEXT UNIQUE,
    created_by      UUID NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Physical seats, reused by every event at the venue.
CREATE TABLE seats (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    venue_id    UUID NOT NULL REFERENCES venues (id) ON DELETE CASCADE,
    section     VARCHAR(50) NOT NULL,
    row_label   VARCHAR(10) NOT NULL,
    seat_number INTEGER NOT NULL CHECK (seat_number > 0),
    pos_x       NUMERIC(8, 2),  -- position on the seat map UI
    pos_y       NUMERIC(8, 2),
    UNIQUE (venue_id, section, row_label, seat_number),
    UNIQUE (id, venue_id)
);

CREATE TABLE events (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organizer_id          UUID NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
    venue_id              UUID NOT NULL REFERENCES venues (id) ON DELETE RESTRICT,
    category_id           SMALLINT REFERENCES categories (id) ON DELETE SET NULL,
    title                 VARCHAR(200) NOT NULL,
    description           TEXT,
    cover_image_url       TEXT,
    starts_at             TIMESTAMPTZ NOT NULL,
    ends_at               TIMESTAMPTZ NOT NULL,
    status                event_status NOT NULL DEFAULT 'draft',
    seating_mode          seating_mode NOT NULL DEFAULT 'reserved',
    capacity              INTEGER CHECK (capacity > 0),
    currency              CHAR(3) NOT NULL DEFAULT 'USD',
    max_tickets_per_order SMALLINT NOT NULL DEFAULT 6
                          CHECK (max_tickets_per_order > 0),
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (ends_at > starts_at),
    CHECK (seating_mode = 'reserved' OR capacity IS NOT NULL),
    UNIQUE (id, venue_id)
);

-- Users allowed to scan tickets at an event.
CREATE TABLE event_staff (
    event_id UUID NOT NULL REFERENCES events (id) ON DELETE CASCADE,
    user_id  UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    PRIMARY KEY (event_id, user_id)
);

CREATE TABLE ticket_tiers (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id    UUID NOT NULL REFERENCES events (id) ON DELETE CASCADE,
    name        VARCHAR(80) NOT NULL,
    price_cents INTEGER NOT NULL CHECK (price_cents >= 0),
    UNIQUE (event_id, name),
    UNIQUE (id, event_id)
);

-- One sellable row per physical seat per event.
-- The composite foreign keys guarantee the seat is in the event's venue
-- and the tier belongs to the same event.
CREATE TABLE event_seats (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id        UUID NOT NULL,
    venue_id        UUID NOT NULL,
    seat_id         UUID NOT NULL,
    tier_id         UUID NOT NULL,
    status          seat_status NOT NULL DEFAULT 'available',
    held_by         UUID REFERENCES users (id) ON DELETE SET NULL,
    hold_expires_at TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (event_id, seat_id),
    UNIQUE (id, event_id),
    FOREIGN KEY (event_id, venue_id) REFERENCES events (id, venue_id) ON DELETE CASCADE,
    FOREIGN KEY (seat_id, venue_id)  REFERENCES seats (id, venue_id)  ON DELETE RESTRICT,
    FOREIGN KEY (tier_id, event_id)  REFERENCES ticket_tiers (id, event_id) ON DELETE RESTRICT,
    CONSTRAINT event_seats_hold_state CHECK (
        (status = 'held' AND held_by IS NOT NULL AND hold_expires_at IS NOT NULL)
        OR (status <> 'held' AND held_by IS NULL AND hold_expires_at IS NULL)
    )
);

CREATE TABLE orders (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           UUID NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
    event_id          UUID NOT NULL REFERENCES events (id) ON DELETE RESTRICT,
    status            order_status NOT NULL DEFAULT 'confirmed',
    total_cents       INTEGER NOT NULL CHECK (total_cents >= 0),
    currency          CHAR(3) NOT NULL,
    payment_reference TEXT UNIQUE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (id, event_id)
);

CREATE TABLE tickets (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id       UUID NOT NULL,
    event_id       UUID NOT NULL,
    owner_id       UUID NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
    tier_id        UUID NOT NULL,
    event_seat_id  UUID,  -- NULL for general admission
    price_cents    INTEGER NOT NULL CHECK (price_cents >= 0),
    status         ticket_status NOT NULL DEFAULT 'valid',
    -- The API rebuilds the same QR from AES-256-GCM(server key, qr_nonce, ticket id).
    -- The key stays out of the database, so a DB leak cannot forge QR codes.
    qr_nonce       BYTEA NOT NULL UNIQUE DEFAULT gen_random_bytes(12)
                   CHECK (octet_length(qr_nonce) = 12),
    qr_key_version SMALLINT NOT NULL DEFAULT 1 CHECK (qr_key_version > 0),
    checked_in_at  TIMESTAMPTZ,
    cancelled_at   TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (order_id, event_id)      REFERENCES orders (id, event_id)       ON DELETE RESTRICT,
    FOREIGN KEY (tier_id, event_id)       REFERENCES ticket_tiers (id, event_id) ON DELETE RESTRICT,
    FOREIGN KEY (event_seat_id, event_id) REFERENCES event_seats (id, event_id)  ON DELETE RESTRICT,
    CHECK ((status = 'used') = (checked_in_at IS NOT NULL)),
    CHECK ((status = 'cancelled') = (cancelled_at IS NOT NULL))
);

-- Audit log of every scan attempt, including rejected ones.
CREATE TABLE ticket_scans (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ticket_id  UUID REFERENCES tickets (id) ON DELETE SET NULL,
    event_id   UUID NOT NULL REFERENCES events (id) ON DELETE CASCADE,
    scanned_by UUID NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
    result     scan_result NOT NULL,
    scanned_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ===========================================================
-- Indexes
-- ===========================================================
CREATE INDEX idx_venues_location       ON venues USING GIST (location);
CREATE INDEX idx_events_status_starts  ON events (status, starts_at);
CREATE INDEX idx_events_venue          ON events (venue_id);
CREATE INDEX idx_events_organizer      ON events (organizer_id);
CREATE INDEX idx_event_seats_status    ON event_seats (event_id, status);
CREATE INDEX idx_event_seats_expiry    ON event_seats (hold_expires_at) WHERE status = 'held';
CREATE INDEX idx_orders_user           ON orders (user_id);
CREATE INDEX idx_tickets_owner         ON tickets (owner_id);
CREATE INDEX idx_tickets_event_status  ON tickets (event_id, status);
CREATE INDEX idx_tickets_order         ON tickets (order_id);
CREATE INDEX idx_ticket_scans_event    ON ticket_scans (event_id, scanned_at DESC);

-- Final safety net: a seat can never have two live tickets.
CREATE UNIQUE INDEX uq_live_ticket_per_seat
    ON tickets (event_seat_id)
    WHERE event_seat_id IS NOT NULL AND status IN ('valid', 'used');

-- ===========================================================
-- Triggers
-- ===========================================================
CREATE FUNCTION set_updated_at() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_users_updated       BEFORE UPDATE ON users       FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_venues_updated      BEFORE UPDATE ON venues      FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_events_updated      BEFORE UPDATE ON events      FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_event_seats_updated BEFORE UPDATE ON event_seats FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_orders_updated      BEFORE UPDATE ON orders      FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_tickets_updated     BEFORE UPDATE ON tickets     FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Keeps each ticket's QR code fixed for its lifetime.
CREATE FUNCTION prevent_qr_change() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.id IS DISTINCT FROM OLD.id
       OR NEW.qr_nonce IS DISTINCT FROM OLD.qr_nonce
       OR NEW.qr_key_version IS DISTINCT FROM OLD.qr_key_version THEN
        RAISE EXCEPTION 'Ticket identity and QR data are immutable'
            USING ERRCODE = 'EH006';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_tickets_qr_immutable
    BEFORE UPDATE ON tickets
    FOR EACH ROW EXECUTE FUNCTION prevent_qr_change();

-- ===========================================================
-- Booking logic
--   EH001 seat unavailable        EH002 event not bookable
--   EH003 hold missing/expired    EH004 ticket not cancellable
--   EH005 ticket limit exceeded   EH006 immutable ticket data
--   EH007 invalid request         EH008 sold out
-- clock_timestamp() is used because now() is frozen at transaction
-- start and would be stale after waiting on a row lock.
-- ===========================================================
CREATE FUNCTION assert_event_bookable(p_event_id UUID, p_mode seating_mode)
RETURNS events
LANGUAGE plpgsql AS $$
DECLARE
    v_event events%ROWTYPE;
BEGIN
    SELECT * INTO v_event FROM events WHERE id = p_event_id;

    IF NOT FOUND
       OR v_event.status <> 'published'
       OR v_event.seating_mode <> p_mode
       OR v_event.starts_at <= clock_timestamp() THEN
        RAISE EXCEPTION 'Event % is not open for booking', p_event_id
            USING ERRCODE = 'EH002';
    END IF;

    RETURN v_event;
END;
$$;

-- All-or-nothing seat hold. Returns the earliest expiry among the seats.
-- Re-holding your own seat is idempotent and does not extend the timer.
CREATE FUNCTION hold_seats(
    p_event_id UUID,
    p_user_id UUID,
    p_event_seat_ids UUID[],
    p_ttl INTERVAL DEFAULT INTERVAL '10 minutes'
) RETURNS TIMESTAMPTZ
LANGUAGE plpgsql AS $$
DECLARE
    v_event     events%ROWTYPE;
    v_requested INTEGER;
    v_updated   INTEGER;
    v_held      INTEGER;
    v_expires   TIMESTAMPTZ;
BEGIN
    v_event := assert_event_bookable(p_event_id, 'reserved');

    SELECT count(DISTINCT s) INTO v_requested FROM unnest(p_event_seat_ids) AS s;
    IF v_requested = 0 THEN
        RAISE EXCEPTION 'No seats requested' USING ERRCODE = 'EH007';
    END IF;

    -- Serializes one user's concurrent requests so the limit stays exact.
    PERFORM pg_advisory_xact_lock(hashtextextended(p_event_id::TEXT || p_user_id::TEXT, 0));

    -- Consistent lock order prevents deadlocks between overlapping requests.
    PERFORM 1
    FROM event_seats
    WHERE event_id = p_event_id AND id = ANY (p_event_seat_ids)
    ORDER BY id
    FOR UPDATE;

    v_expires := clock_timestamp() + p_ttl;

    UPDATE event_seats
    SET hold_expires_at = CASE
            WHEN status = 'held' AND held_by = p_user_id
                 AND hold_expires_at > clock_timestamp()
            THEN hold_expires_at
            ELSE v_expires
        END,
        status = 'held',
        held_by = p_user_id
    WHERE event_id = p_event_id
      AND id = ANY (p_event_seat_ids)
      AND (
          status = 'available'
          OR (status = 'held' AND (held_by = p_user_id OR hold_expires_at <= clock_timestamp()))
      );

    GET DIAGNOSTICS v_updated = ROW_COUNT;
    IF v_updated <> v_requested THEN
        RAISE EXCEPTION 'One or more seats are unavailable' USING ERRCODE = 'EH001';
    END IF;

    SELECT count(*) INTO v_held
    FROM event_seats
    WHERE event_id = p_event_id
      AND status = 'held'
      AND held_by = p_user_id
      AND hold_expires_at > clock_timestamp();

    IF v_held > v_event.max_tickets_per_order THEN
        RAISE EXCEPTION 'Limit of % tickets exceeded', v_event.max_tickets_per_order
            USING ERRCODE = 'EH005';
    END IF;

    RETURN (
        SELECT min(hold_expires_at)
        FROM event_seats
        WHERE event_id = p_event_id AND id = ANY (p_event_seat_ids)
    );
END;
$$;

-- Returns the released seat ids so the API can broadcast them.
CREATE FUNCTION release_seats(p_event_id UUID, p_user_id UUID, p_event_seat_ids UUID[])
RETURNS SETOF UUID
LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    UPDATE event_seats AS es
    SET status = 'available', held_by = NULL, hold_expires_at = NULL
    WHERE es.event_id = p_event_id
      AND es.id = ANY (p_event_seat_ids)
      AND es.status = 'held'
      AND es.held_by = p_user_id
    RETURNING es.id;
END;
$$;

-- For a periodic background task. Bookings already ignore expired holds,
-- so this only cleans up rows and supplies seats to broadcast.
CREATE FUNCTION release_expired_holds()
RETURNS TABLE (expired_event_id UUID, expired_seat_id UUID)
LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    WITH expired AS (
        SELECT es.id
        FROM event_seats AS es
        WHERE es.status = 'held' AND es.hold_expires_at <= clock_timestamp()
        ORDER BY es.id
        FOR UPDATE SKIP LOCKED
    )
    UPDATE event_seats AS es
    SET status = 'available', held_by = NULL, hold_expires_at = NULL
    FROM expired
    WHERE es.id = expired.id
    RETURNING es.event_id, es.id;
END;
$$;

-- Converts the user's active holds into an order and tickets.
CREATE FUNCTION confirm_booking(
    p_event_id UUID,
    p_user_id UUID,
    p_event_seat_ids UUID[],
    p_payment_reference TEXT DEFAULT NULL
) RETURNS UUID
LANGUAGE plpgsql AS $$
DECLARE
    v_event     events%ROWTYPE;
    v_requested INTEGER;
    v_valid     INTEGER;
    v_total     INTEGER;
    v_order_id  UUID;
BEGIN
    v_event := assert_event_bookable(p_event_id, 'reserved');

    SELECT count(DISTINCT s) INTO v_requested FROM unnest(p_event_seat_ids) AS s;
    IF v_requested = 0 THEN
        RAISE EXCEPTION 'No seats requested' USING ERRCODE = 'EH007';
    END IF;

    PERFORM 1
    FROM event_seats
    WHERE event_id = p_event_id AND id = ANY (p_event_seat_ids)
    ORDER BY id
    FOR UPDATE;

    SELECT count(*), COALESCE(sum(t.price_cents), 0)
    INTO v_valid, v_total
    FROM event_seats AS es
    JOIN ticket_tiers AS t ON t.id = es.tier_id
    WHERE es.event_id = p_event_id
      AND es.id = ANY (p_event_seat_ids)
      AND es.status = 'held'
      AND es.held_by = p_user_id
      AND es.hold_expires_at > clock_timestamp();

    IF v_valid <> v_requested THEN
        RAISE EXCEPTION 'A seat hold is missing or expired' USING ERRCODE = 'EH003';
    END IF;

    INSERT INTO orders (user_id, event_id, total_cents, currency, payment_reference)
    VALUES (p_user_id, p_event_id, v_total, v_event.currency, p_payment_reference)
    RETURNING id INTO v_order_id;

    UPDATE event_seats
    SET status = 'booked', held_by = NULL, hold_expires_at = NULL
    WHERE event_id = p_event_id AND id = ANY (p_event_seat_ids);

    INSERT INTO tickets (order_id, event_id, owner_id, tier_id, event_seat_id, price_cents)
    SELECT v_order_id, es.event_id, p_user_id, es.tier_id, es.id, t.price_cents
    FROM event_seats AS es
    JOIN ticket_tiers AS t ON t.id = es.tier_id
    WHERE es.event_id = p_event_id AND es.id = ANY (p_event_seat_ids);

    RETURN v_order_id;
END;
$$;

-- Unseated events: the event row lock makes the capacity check atomic.
-- FOR NO KEY UPDATE does not conflict with foreign-key checks.
CREATE FUNCTION book_general_admission(
    p_event_id UUID,
    p_user_id UUID,
    p_tier_id UUID,
    p_quantity INTEGER,
    p_payment_reference TEXT DEFAULT NULL
) RETURNS UUID
LANGUAGE plpgsql AS $$
DECLARE
    v_event    events%ROWTYPE;
    v_price    INTEGER;
    v_sold     INTEGER;
    v_order_id UUID;
BEGIN
    PERFORM 1 FROM events WHERE id = p_event_id FOR NO KEY UPDATE;
    v_event := assert_event_bookable(p_event_id, 'general');

    IF p_quantity IS NULL OR p_quantity < 1 THEN
        RAISE EXCEPTION 'Quantity must be positive' USING ERRCODE = 'EH007';
    END IF;

    IF p_quantity > v_event.max_tickets_per_order THEN
        RAISE EXCEPTION 'Limit of % tickets exceeded', v_event.max_tickets_per_order
            USING ERRCODE = 'EH005';
    END IF;

    SELECT price_cents INTO v_price
    FROM ticket_tiers
    WHERE id = p_tier_id AND event_id = p_event_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Ticket tier not found for this event' USING ERRCODE = 'EH007';
    END IF;

    SELECT count(*) INTO v_sold
    FROM tickets
    WHERE event_id = p_event_id AND status IN ('valid', 'used');

    IF v_sold + p_quantity > v_event.capacity THEN
        RAISE EXCEPTION 'Not enough tickets remaining' USING ERRCODE = 'EH008';
    END IF;

    INSERT INTO orders (user_id, event_id, total_cents, currency, payment_reference)
    VALUES (p_user_id, p_event_id, v_price * p_quantity, v_event.currency, p_payment_reference)
    RETURNING id INTO v_order_id;

    INSERT INTO tickets (order_id, event_id, owner_id, tier_id, price_cents)
    SELECT v_order_id, p_event_id, p_user_id, p_tier_id, v_price
    FROM generate_series(1, p_quantity);

    RETURN v_order_id;
END;
$$;

-- Returns the freed seat id, or NULL for general admission.
CREATE FUNCTION cancel_ticket(p_ticket_id UUID)
RETURNS UUID
LANGUAGE plpgsql AS $$
DECLARE
    v_seat_id UUID;
BEGIN
    SELECT event_seat_id INTO v_seat_id
    FROM tickets
    WHERE id = p_ticket_id AND status = 'valid'
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Ticket cannot be cancelled' USING ERRCODE = 'EH004';
    END IF;

    UPDATE tickets
    SET status = 'cancelled', cancelled_at = clock_timestamp()
    WHERE id = p_ticket_id;

    IF v_seat_id IS NOT NULL THEN
        UPDATE event_seats
        SET status = 'available'
        WHERE id = v_seat_id AND status = 'booked';
    END IF;

    RETURN v_seat_id;
END;
$$;

-- Called after the API decrypts the QR. The row lock makes two
-- simultaneous scans resolve to one 'accepted' and one 'already_used'.
CREATE FUNCTION check_in_ticket(p_ticket_id UUID, p_event_id UUID, p_scanner_id UUID)
RETURNS scan_result
LANGUAGE plpgsql AS $$
DECLARE
    v_ticket tickets%ROWTYPE;
    v_result scan_result;
BEGIN
    SELECT * INTO v_ticket FROM tickets WHERE id = p_ticket_id FOR UPDATE;

    IF NOT EXISTS (
        SELECT 1
        FROM events AS e
        WHERE e.id = p_event_id
          AND (
              e.organizer_id = p_scanner_id
              OR EXISTS (
                  SELECT 1 FROM event_staff AS s
                  WHERE s.event_id = e.id AND s.user_id = p_scanner_id
              )
              OR EXISTS (
                  SELECT 1 FROM users AS u
                  WHERE u.id = p_scanner_id AND u.role = 'admin' AND u.is_active
              )
          )
    ) THEN
        v_result := 'unauthorized';
    ELSIF v_ticket.id IS NULL THEN
        v_result := 'invalid';
    ELSIF v_ticket.event_id <> p_event_id THEN
        v_result := 'wrong_event';
    ELSIF v_ticket.status = 'cancelled' THEN
        v_result := 'cancelled';
    ELSIF v_ticket.status = 'used' THEN
        v_result := 'already_used';
    ELSE
        UPDATE tickets
        SET status = 'used', checked_in_at = clock_timestamp()
        WHERE id = p_ticket_id;
        v_result := 'accepted';
    END IF;

    INSERT INTO ticket_scans (ticket_id, event_id, scanned_by, result)
    VALUES (v_ticket.id, p_event_id, p_scanner_id, v_result);

    RETURN v_result;
END;
$$;

COMMIT;