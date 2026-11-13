import { useMemo, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";

import { api, errorMessage } from "../api/client";
import type { EventItem, SeatMap, Tier, VenueSeat } from "../api/types";
import { useApi } from "../hooks/useApi";
import { formatDate, formatMoney } from "../lib/format";

export default function ManageEventPage() {
  const { t } = useTranslation();
  const { eventId = "" } = useParams();
  const event = useApi(() => api.get<EventItem>(`/events/${eventId}`), [eventId]);
  const tiers = useApi(() => api.get<Tier[]>(`/events/${eventId}/tiers`), [eventId]);
  const seatMap = useApi(() => api.get<SeatMap>(`/events/${eventId}/seats`), [eventId]);
  const venueId = event.data?.venue_id;
  const venueSeats = useApi(
    () => (venueId ? api.get<VenueSeat[]>(`/venues/${venueId}/seats`) : Promise.resolve([])),
    [venueId],
  );

  const [tierName, setTierName] = useState("");
  const [tierPrice, setTierPrice] = useState("0");
  const [section, setSection] = useState("Main");
  const [rows, setRows] = useState("A,B,C");
  const [seatsPerRow, setSeatsPerRow] = useState("10");
  const [assignTier, setAssignTier] = useState("");
  const [assignSection, setAssignSection] = useState("");
  const [staffEmail, setStaffEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const sections = useMemo(
    () => [...new Set((venueSeats.data ?? []).map((seat) => seat.section))],
    [venueSeats.data],
  );

  const run = async (action: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
      await Promise.all([event.reload(), tiers.reload(), seatMap.reload(), venueSeats.reload()]);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  };

  const addTier = (formEvent: FormEvent) => {
    formEvent.preventDefault();
    void run(async () => {
      await api.post(`/events/${eventId}/tiers`, {
        name: tierName,
        price_cents: Math.round(Number(tierPrice) * 100),
      });
      setTierName("");
      setTierPrice("0");
    });
  };

  const addLayout = (formEvent: FormEvent) => {
    formEvent.preventDefault();
    const rowLabels = rows.split(",").map((row) => row.trim()).filter(Boolean);
    const lowestY = Math.max(-80, ...(venueSeats.data ?? []).map((seat) => seat.pos_y ?? 0));

    void run(() =>
      api.post(`/venues/${venueId}/seats/bulk`, {
        blocks: [
          {
            section,
            row_labels: rowLabels,
            seats_per_row: Number(seatsPerRow),
            origin_y: lowestY + 80,
          },
        ],
      }),
    );
  };

  const assignSeats = (formEvent: FormEvent) => {
    formEvent.preventDefault();
    const tierId = assignTier || tiers.data?.[0]?.id;
    if (!tierId) return;

    void run(() =>
      api.post(`/events/${eventId}/seats/assign`, {
        assignments: [
          { tier_id: tierId, sections: assignSection ? [assignSection] : null },
        ],
      }),
    );
  };

  const addStaff = (formEvent: FormEvent) => {
    formEvent.preventDefault();
    void run(async () => {
      await api.post(`/events/${eventId}/staff`, { email: staffEmail });
      setStaffEmail("");
    });
  };

  if (event.error) return <div className="alert-error">{event.error}</div>;
  if (!event.data) return <p className="text-sm text-slate-500">{t("event.loading")}</p>;

  const current = event.data;
  const isDraft = current.status === "draft";
  const isReserved = current.seating_mode === "reserved";
  const assignedSeats = seatMap.data?.seats.length ?? 0;
  const ready = (tiers.data?.length ?? 0) > 0 && (!isReserved || assignedSeats > 0);

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <header>
        <p className="text-sm font-semibold text-indigo-700">{t(`eventStatus.${current.status}`)}</p>
        <h1 className="text-2xl font-bold">{current.title}</h1>
        <p className="text-sm text-slate-600">
          {formatDate(current.starts_at)} · {current.venue_name}
        </p>
        <Link className="text-sm text-indigo-700 underline" to={`/events/${current.id}`}>
          {t("manage.event.viewPage")}
        </Link>
      </header>

      {error && <div className="alert-error">{error}</div>}

      <section className="card space-y-3">
        <h2 className="font-semibold">{t("manage.event.tiers", { step: 1 })}</h2>
        <ul className="divide-y divide-slate-100 text-sm">
          {tiers.data?.map((tier) => (
            <li key={tier.id} className="flex items-center justify-between gap-3 py-2">
              <span>{tier.name} — {formatMoney(tier.price_cents, current.currency)}</span>
              {isDraft && (
                <button type="button" className="text-red-700 underline" disabled={busy}
                  onClick={() => void run(() => api.delete(`/events/${eventId}/tiers/${tier.id}`))}>
                  {t("common.remove")}
                </button>
              )}
            </li>
          ))}
        </ul>
        {isDraft && (
          <form onSubmit={addTier} className="grid gap-2 sm:grid-cols-[1fr_8rem_auto]">
            <input className="input" placeholder={t("manage.event.tierNamePlaceholder")}
              aria-label={t("manage.event.tierName")} required
              value={tierName} onChange={(e) => setTierName(e.target.value)} />
            <input className="input" type="number" min={0} step="0.01"
              aria-label={t("manage.event.tierPrice")} required
              value={tierPrice} onChange={(e) => setTierPrice(e.target.value)} />
            <button className="btn-secondary" disabled={busy}>{t("manage.event.addTier")}</button>
          </form>
        )}
      </section>

      {isReserved && (
        <section className="card space-y-3">
          <h2 className="font-semibold">{t("manage.event.seats", { step: 2 })}</h2>
          <p className="text-sm text-slate-600">
            {t("manage.event.seatSummary", {
              venueSeats: venueSeats.data?.length ?? 0,
              assigned: assignedSeats,
            })}
          </p>

          {isDraft && (
            <>
              <form onSubmit={addLayout} className="grid gap-2 sm:grid-cols-[1fr_1fr_7rem_auto]">
                <input className="input" aria-label={t("manage.event.section")} required value={section}
                  onChange={(e) => setSection(e.target.value)} />
                <input className="input" aria-label={t("manage.event.rows")} required value={rows}
                  onChange={(e) => setRows(e.target.value)} />
                <input className="input" type="number" min={1} max={500}
                  aria-label={t("manage.event.seatsPerRow")} required
                  value={seatsPerRow} onChange={(e) => setSeatsPerRow(e.target.value)} />
                <button className="btn-secondary" disabled={busy}>{t("manage.event.addSeats")}</button>
              </form>

              <form onSubmit={assignSeats} className="grid gap-2 sm:grid-cols-[1fr_1fr_auto]">
                <select className="input" aria-label={t("manage.event.tier")} value={assignTier}
                  onChange={(e) => setAssignTier(e.target.value)}>
                  {tiers.data?.map((tier) => (
                    <option key={tier.id} value={tier.id}>{tier.name}</option>
                  ))}
                </select>
                <select className="input" aria-label={t("manage.event.sectionToAssign")} value={assignSection}
                  onChange={(e) => setAssignSection(e.target.value)}>
                  <option value="">{t("manage.event.allSections")}</option>
                  {sections.map((name) => <option key={name} value={name}>{name}</option>)}
                </select>
                <button className="btn-secondary" disabled={busy || !tiers.data?.length}>
                  {t("manage.event.assignSeats")}
                </button>
              </form>
            </>
          )}
        </section>
      )}

      <section className="card space-y-3">
        <h2 className="font-semibold">{t("manage.event.staff", { step: isReserved ? 3 : 2 })}</h2>
        <form onSubmit={addStaff} className="flex gap-2">
          <input className="input" type="email" placeholder="staff@example.com"
            aria-label={t("manage.event.staffEmail")}
            required value={staffEmail} onChange={(e) => setStaffEmail(e.target.value)} />
          <button className="btn-secondary" disabled={busy}>{t("common.add")}</button>
        </form>
      </section>

      <section className="card flex flex-wrap gap-2">
        {isDraft && (
          <button type="button" className="btn-primary" disabled={busy || !ready}
            onClick={() => void run(() => api.post(`/events/${eventId}/publish`))}>
            {t("manage.event.publish")}
          </button>
        )}
        {(isDraft || current.status === "published") && (
          <button type="button" className="btn-danger" disabled={busy}
            onClick={() => {
              if (window.confirm(t("manage.event.cancelConfirm"))) {
                void run(() => api.post(`/events/${eventId}/cancel`));
              }
            }}>
            {t("manage.event.cancel")}
          </button>
        )}
        {isDraft && !ready && (
          <p className="w-full text-sm text-slate-600">
            {isReserved ? t("manage.event.requirementReserved") : t("manage.event.requirementGeneral")}
          </p>
        )}
      </section>
    </div>
  );
}