BEGIN;

DO $$
DECLARE
    u1 UUID := gen_random_uuid();
    u2 UUID := gen_random_uuid();
    v  UUID := gen_random_uuid();
    s  UUID := gen_random_uuid();
    e  UUID := gen_random_uuid();
    t  UUID := gen_random_uuid();
    es UUID := gen_random_uuid();
    o  UUID;
BEGIN
    INSERT INTO users (id, email, password_hash, full_name) VALUES
        (u1, 'one@test.local', 'x', 'User One'),
        (u2, 'two@test.local', 'x', 'User Two');

    INSERT INTO venues (id, name, address, city, country, location, created_by)
    VALUES (v, 'Hall', 'Street 1', 'Baku', 'Azerbaijan',
            ST_SetSRID(ST_MakePoint(49.8671, 40.4093), 4326)::GEOGRAPHY, u1);

    INSERT INTO seats (id, venue_id, section, row_label, seat_number)
    VALUES (s, v, 'A', '1', 1);

    INSERT INTO events (id, organizer_id, venue_id, title, starts_at, ends_at, status)
    VALUES (e, u1, v, 'Demo', now() + INTERVAL '1 day', now() + INTERVAL '2 days', 'published');

    INSERT INTO ticket_tiers (id, event_id, name, price_cents) VALUES (t, e, 'Standard', 1000);

    INSERT INTO event_seats (id, event_id, venue_id, seat_id, tier_id)
    VALUES (es, e, v, s, t);

    PERFORM hold_seats(e, u1, ARRAY[es]);

    BEGIN
        PERFORM hold_seats(e, u2, ARRAY[es]);
        RAISE EXCEPTION 'FAIL: second user held the same seat';
    EXCEPTION WHEN SQLSTATE 'EH001' THEN
        RAISE NOTICE 'PASS: competing hold rejected';
    END;

    o := confirm_booking(e, u1, ARRAY[es]);
    RAISE NOTICE 'PASS: booking confirmed';

    BEGIN
        INSERT INTO tickets (order_id, event_id, owner_id, tier_id, event_seat_id, price_cents)
        VALUES (o, e, u2, t, es, 1000);
        RAISE EXCEPTION 'FAIL: duplicate ticket inserted';
    EXCEPTION WHEN unique_violation THEN
        RAISE NOTICE 'PASS: duplicate ticket blocked by unique index';
    END;
END;
$$;

ROLLBACK;