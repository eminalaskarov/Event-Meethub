import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router-dom";

import { api, ApiError, errorMessage } from "../api/client";
import type {
  EventItem,
  HoldResponse,
  LiveSeat,
  Order,
  ReleaseResponse,
} from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { useSeatMap } from "../hooks/useSeatMap";
import { formatMoney, seatShortLabel } from "../lib/format";

const SEAT_SIZE = 32;
const GRID_GAP = 40;

function seatClass(seat: LiveSeat): string {
  if (seat.held_by_me) return "bg-indigo-600 text-white ring-2 ring-indigo-300";
  if (seat.status === "available") return "bg-emerald-500 text-white hover:bg-emerald-600";
  if (seat.status === "held") return "bg-amber-400 text-amber-950 cursor-not-allowed";
  return "bg-slate-300 text-slate-500 cursor-not-allowed";
}

function placeSeats(seats: LiveSeat[]) {
  const rows = [...new Set(seats.map((seat) => `${seat.section}:${seat.row_label}`))];
  const placed = seats.map((seat) => ({
    seat,
    x: seat.pos_x ?? (seat.seat_number - 1) * GRID_GAP,
    y: seat.pos_y ?? rows.indexOf(`${seat.section}:${seat.row_label}`) * GRID_GAP,
  }));

  if (placed.length === 0) return { placed, width: 0, height: 0 };

  const minX = Math.min(...placed.map((item) => item.x));
  const minY = Math.min(...placed.map((item) => item.y));
  const adjusted = placed.map((item) => ({ ...item, x: item.x - minX, y: item.y - minY }));

  return {
    placed: adjusted,
    width: Math.max(...adjusted.map((item) => item.x)) + SEAT_SIZE,
    height: Math.max(...adjusted.map((item) => item.y)) + SEAT_SIZE,
  };
}

function LegendItem({ className, label }: { className: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className={`h-3.5 w-3.5 rounded ${className}`} />
      {label}
    </span>
  );
}

export default function SeatPlan({ event }: { event: EventItem }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const { map, status, error, clockOffset, refresh, markHeld, markReleased } = useSeatMap(event.id);
  const [busySeats, setBusySeats] = useState<Set<string>>(new Set());
  const [confirming, setConfirming] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const layout = useMemo(() => placeSeats(map?.seats ?? []), [map?.seats]);
  const mySeats = useMemo(
    () => (map?.seats ?? []).filter((seat) => seat.held_by_me),
    [map?.seats],
  );

  const total = mySeats.reduce((sum, seat) => sum + seat.price_cents, 0);
  const earliestExpiry = mySeats.length
    ? Math.min(...mySeats.map((seat) => Date.parse(seat.hold_expires_at ?? "")))
    : null;
  const secondsLeft =
    earliestExpiry === null
      ? 0
      : Math.max(0, Math.ceil((earliestExpiry - (now + clockOffset)) / 1000));

  const readOnly = event.status !== "published";

  const setSeatBusy = (id: string, busy: boolean) => {
    setBusySeats((current) => {
      const next = new Set(current);
      if (busy) next.add(id);
      else next.delete(id);
      return next;
    });
  };

  const toggleSeat = async (seat: LiveSeat) => {
    if (readOnly || busySeats.has(seat.event_seat_id)) return;
    if (!user) {
      navigate("/login", { state: { from: location.pathname } });
      return;
    }

    setActionError(null);
    setSeatBusy(seat.event_seat_id, true);

    try {
      if (seat.held_by_me) {
        const result = await api.delete<ReleaseResponse>(
          `/events/${event.id}/holds?event_seat_id=${seat.event_seat_id}`,
        );
        markReleased(result.released_event_seat_ids);
      } else if (seat.status === "available") {
        const result = await api.post<HoldResponse>(`/events/${event.id}/holds`, {
          event_seat_ids: [seat.event_seat_id],
        });
        markHeld(result.event_seat_ids, result.hold_expires_at);
      }
    } catch (caught) {
      setActionError(errorMessage(caught));
      if (caught instanceof ApiError && caught.status === 409) await refresh();
    } finally {
      setSeatBusy(seat.event_seat_id, false);
    }
  };

  const confirm = async () => {
    setConfirming(true);
    setActionError(null);

    try {
      await api.post<Order>(`/events/${event.id}/confirm`, {
        event_seat_ids: mySeats.map((seat) => seat.event_seat_id),
      });
      navigate("/wallet");
    } catch (caught) {
      setActionError(errorMessage(caught));
      await refresh();
    } finally {
      setConfirming(false);
    }
  };

  if (error && !map) return <div className="alert-error">{error}</div>;
  if (!map) return <p className="text-sm text-slate-500">{t("seatPlan.loading")}</p>;

  const statusLabel = {
    connecting: t("seatPlan.connecting"),
    live: t("common.live"),
    offline: t("seatPlan.reconnecting"),
  }[status];

  const seatStatusLabel = (seat: LiveSeat) =>
    seat.held_by_me ? t("seatStatus.mine") : t(`seatStatus.${seat.status}`);

  const countdown = `${Math.floor(secondsLeft / 60)}:${String(secondsLeft % 60).padStart(2, "0")}`;

  return (
    <div className="grid gap-5 lg:grid-cols-[1fr_20rem]">
      <section className="card min-w-0">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-semibold">{t("seatPlan.title")}</h2>
          <span
            className={`rounded-full px-2.5 py-1 text-xs font-semibold ${
              status === "live" ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"
            }`}
            aria-live="polite"
          >
            {statusLabel} · {t("seatPlan.availableCount", { count: map.tickets_remaining })}
          </span>
        </div>

        <div className="mb-3 flex flex-wrap gap-3 text-xs text-slate-600">
          <LegendItem className="bg-emerald-500" label={t("seatStatus.available")} />
          <LegendItem className="bg-indigo-600" label={t("seatStatus.mine")} />
          <LegendItem className="bg-amber-400" label={t("seatStatus.held")} />
          <LegendItem className="bg-slate-300" label={t("seatPlan.legendUnavailable")} />
        </div>

        <div className="mb-4 rounded bg-slate-800 py-1 text-center text-xs tracking-widest text-white">
          {t("seatPlan.stage")}
        </div>

        <div className="overflow-auto pb-2">
          <div className="relative mx-auto" style={{ width: layout.width, height: layout.height }}>
            {layout.placed.map(({ seat, x, y }) => {
              const selectable = seat.status === "available" || seat.held_by_me;
              const price = formatMoney(seat.price_cents, event.currency);
              return (
                <button
                  key={seat.event_seat_id}
                  type="button"
                  style={{ left: x, top: y, width: SEAT_SIZE, height: SEAT_SIZE }}
                  className={`absolute rounded-md text-[11px] font-semibold transition ${seatClass(seat)}`}
                  disabled={readOnly || !selectable || busySeats.has(seat.event_seat_id)}
                  aria-label={`${seatShortLabel(seat)}, ${seat.tier_name}, ${price}, ${seatStatusLabel(seat)}`}
                  title={`${seatShortLabel(seat)} · ${seat.tier_name} · ${price}`}
                  onClick={() => void toggleSeat(seat)}
                >
                  {seat.seat_number}
                </button>
              );
            })}
          </div>
        </div>
      </section>

      <aside className="card h-fit lg:sticky lg:top-20">
        <h2 className="text-lg font-semibold">{t("seatPlan.selection")}</h2>
        {actionError && <div className="alert-error mt-3">{actionError}</div>}

        {mySeats.length === 0 ? (
          <p className="mt-3 text-sm text-slate-500">
            {readOnly ? t("seatPlan.bookingClosed") : t("seatPlan.tapSeat")}
          </p>
        ) : (
          <>
            <ul className="mt-3 space-y-2 text-sm">
              {mySeats.map((seat) => (
                <li key={seat.event_seat_id} className="flex justify-between gap-3">
                  <span>{seatShortLabel(seat)}</span>
                  <span className="font-medium">{formatMoney(seat.price_cents, event.currency)}</span>
                </li>
              ))}
            </ul>
            <div className="mt-4 flex justify-between border-t border-slate-200 pt-3 font-semibold">
              <span>{t("common.total")}</span>
              <span>{formatMoney(total, event.currency)}</span>
            </div>
            <p className="mt-2 text-sm text-amber-700" aria-live="off">
              {t("seatPlan.heldFor", { time: countdown })}
            </p>
            <button
              type="button"
              className="btn-primary mt-4 w-full"
              disabled={confirming || secondsLeft === 0}
              onClick={() => void confirm()}
            >
              {confirming ? t("seatPlan.confirming") : t("seatPlan.confirm")}
            </button>
            <p className="mt-2 text-xs text-slate-500">{t("common.demoCheckout")}</p>
          </>
        )}
      </aside>
    </div>
  );
}