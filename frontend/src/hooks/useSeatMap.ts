import { useCallback, useEffect, useRef, useState } from "react";

import { api, errorMessage, WS_URL } from "../api/client";
import type { RealtimeMessage, SeatMap } from "../api/types";

export type LiveStatus = "connecting" | "live" | "offline";

function countAvailable(map: SeatMap): SeatMap {
  if (map.seating_mode !== "reserved") return map;
  return {
    ...map,
    tickets_remaining: map.seats.filter((seat) => seat.status === "available").length,
  };
}

function applyMessage(map: SeatMap, message: RealtimeMessage): SeatMap {
  if (message.type === "availability.updated") {
    return { ...map, tickets_remaining: message.tickets_remaining };
  }
  if (message.type !== "seats.updated") return map;

  const updates = new Map(message.seats.map((seat) => [seat.event_seat_id, seat]));
  return countAvailable({
    ...map,
    seats: map.seats.map((seat) => {
      const update = updates.get(seat.event_seat_id);
      if (!update) return seat;
      return {
        ...seat,
        status: update.status,
        hold_expires_at: update.hold_expires_at,
        held_by_me: update.status === "held" ? seat.held_by_me : false,
      };
    }),
  });
}

export function useSeatMap(eventId: string) {
  const [map, setMap] = useState<SeatMap | null>(null);
  const [status, setStatus] = useState<LiveStatus>("connecting");
  const [error, setError] = useState<string | null>(null);
  const [clockOffset, setClockOffset] = useState(0);
  const refreshRef = useRef<() => Promise<void>>(async () => undefined);

  useEffect(() => {
    let disposed = false;
    let socket: WebSocket | null = null;
    let retryTimer: number | undefined;
    let attempts = 0;
    let latestLoad = 0;
    let buffer: RealtimeMessage[] | null = null;

    setMap(null);
    setStatus("connecting");
    setError(null);

    const load = async () => {
      const loadId = ++latestLoad;
      buffer = [];

      try {
        const snapshot = await api.get<SeatMap>(`/events/${eventId}/seats`);
        if (disposed || loadId !== latestLoad) return;

        const pending: RealtimeMessage[] = buffer ?? [];
        buffer = null;
        setClockOffset(Date.parse(snapshot.server_time) - Date.now());
        setMap(pending.reduce(applyMessage, snapshot));
        setError(null);
      } catch (caught) {
        if (disposed || loadId !== latestLoad) return;
        buffer = null;
        setError(errorMessage(caught));
      }
    };

    refreshRef.current = load;

    const connect = () => {
      socket = new WebSocket(`${WS_URL}/ws/events/${eventId}/seats`);

      socket.onmessage = (message) => {
        const payload = JSON.parse(message.data as string) as RealtimeMessage;

        if (payload.type === "connected") {
          attempts = 0;
          setStatus("live");
          void load();
        } else if (payload.type === "resync") {
          void load();
        } else if (buffer) {
          buffer.push(payload);
        } else {
          setMap((current) => (current ? applyMessage(current, payload) : current));
        }
      };

      socket.onclose = (closeEvent) => {
        if (disposed) return;
        setStatus("offline");
        void load();

        // 4404 is expected for draft previews, so don't keep reconnecting.
        if (closeEvent.code === 4404) return;

        const delay = Math.min(1000 * 2 ** attempts, 15000);
        attempts += 1;
        retryTimer = window.setTimeout(connect, delay);
      };
    };

    connect();

    return () => {
      disposed = true;
      window.clearTimeout(retryTimer);
      socket?.close();
    };
  }, [eventId]);

  const refresh = useCallback(() => refreshRef.current(), []);

  const markHeld = useCallback((ids: string[], expiresAt: string) => {
    const selected = new Set(ids);
    setMap((current) =>
      current
        ? countAvailable({
            ...current,
            seats: current.seats.map((seat) =>
              selected.has(seat.event_seat_id)
                ? {
                    ...seat,
                    status: "held",
                    held_by_me: true,
                    hold_expires_at: seat.hold_expires_at ?? expiresAt,
                  }
                : seat,
            ),
          })
        : current,
    );
  }, []);

  const markReleased = useCallback((ids: string[]) => {
    const selected = new Set(ids);
    setMap((current) =>
      current
        ? countAvailable({
            ...current,
            seats: current.seats.map((seat) =>
              selected.has(seat.event_seat_id)
                ? { ...seat, status: "available", held_by_me: false, hold_expires_at: null }
                : seat,
            ),
          })
        : current,
    );
  }, []);

  return { map, status, error, clockOffset, refresh, markHeld, markReleased };
}