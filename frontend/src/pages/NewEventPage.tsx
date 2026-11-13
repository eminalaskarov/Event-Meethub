import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";

import { api, errorMessage } from "../api/client";
import type { EventItem, SeatingMode, Venue } from "../api/types";
import { useApi } from "../hooks/useApi";

export default function NewEventPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const venues = useApi(() => api.get<Venue[]>("/venues?limit=100"), []);
  const [venueId, setVenueId] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [startsAt, setStartsAt] = useState("");
  const [endsAt, setEndsAt] = useState("");
  const [seatingMode, setSeatingMode] = useState<SeatingMode>("reserved");
  const [capacity, setCapacity] = useState("");
  const [currency, setCurrency] = useState("USD");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const created = await api.post<EventItem>("/events", {
        venue_id: venueId,
        title,
        description: description || null,
        starts_at: new Date(startsAt).toISOString(),
        ends_at: new Date(endsAt).toISOString(),
        seating_mode: seatingMode,
        capacity: seatingMode === "general" ? Number(capacity) : null,
        currency: currency.toUpperCase(),
      });
      navigate(`/manage/events/${created.id}`);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={(event) => void submit(event)} className="card mx-auto max-w-xl space-y-4">
      <h1 className="text-2xl font-bold">{t("manage.eventForm.title")}</h1>
      {(error || venues.error) && <div className="alert-error">{error ?? venues.error}</div>}

      <div>
        <label className="label" htmlFor="venue">{t("manage.eventForm.venue")}</label>
        <select id="venue" className="input" required value={venueId}
          onChange={(e) => setVenueId(e.target.value)}>
          <option value="">{t("manage.eventForm.selectVenue")}</option>
          {venues.data?.map((venue) => (
            <option key={venue.id} value={venue.id}>{venue.name}, {venue.city}</option>
          ))}
        </select>
        <Link className="mt-1 inline-block text-sm text-indigo-700 underline" to="/manage/venues/new">
          {t("manage.eventForm.addVenue")}
        </Link>
      </div>

      <div>
        <label className="label" htmlFor="title">{t("manage.eventForm.name")}</label>
        <input id="title" className="input" required maxLength={200} value={title}
          onChange={(e) => setTitle(e.target.value)} />
      </div>

      <div>
        <label className="label" htmlFor="description">{t("manage.eventForm.description")}</label>
        <textarea id="description" className="input" rows={4} value={description}
          onChange={(e) => setDescription(e.target.value)} />
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label className="label" htmlFor="starts">{t("manage.eventForm.starts")}</label>
          <input id="starts" className="input" type="datetime-local" required value={startsAt}
            onChange={(e) => setStartsAt(e.target.value)} />
        </div>
        <div>
          <label className="label" htmlFor="ends">{t("manage.eventForm.ends")}</label>
          <input id="ends" className="input" type="datetime-local" required value={endsAt}
            onChange={(e) => setEndsAt(e.target.value)} />
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label className="label" htmlFor="mode">{t("manage.eventForm.seating")}</label>
          <select id="mode" className="input" value={seatingMode}
            onChange={(e) => setSeatingMode(e.target.value as SeatingMode)}>
            <option value="reserved">{t("manage.eventForm.reserved")}</option>
            <option value="general">{t("manage.eventForm.general")}</option>
          </select>
        </div>
        <div>
          <label className="label" htmlFor="currency">{t("manage.eventForm.currency")}</label>
          <input id="currency" className="input" required pattern="[A-Za-z]{3}" maxLength={3}
            value={currency} onChange={(e) => setCurrency(e.target.value)} />
        </div>
      </div>

      {seatingMode === "general" && (
        <div>
          <label className="label" htmlFor="capacity">{t("manage.eventForm.capacity")}</label>
          <input id="capacity" className="input" type="number" min={1} required value={capacity}
            onChange={(e) => setCapacity(e.target.value)} />
        </div>
      )}

      <button className="btn-primary w-full" disabled={busy}>
        {busy ? t("manage.eventForm.creating") : t("manage.eventForm.create")}
      </button>
    </form>
  );
}