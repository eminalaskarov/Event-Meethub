import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";

import { api } from "../api/client";
import type { EventItem } from "../api/types";
import GeneralBooking from "../components/GeneralBooking";
import SeatPlan from "../components/SeatPlan";
import { useApi } from "../hooks/useApi";
import { formatDate } from "../lib/format";

export default function EventDetailPage() {
  const { t } = useTranslation();
  const { eventId = "" } = useParams();
  const { data: event, loading, error } = useApi(
    () => api.get<EventItem>(`/events/${eventId}`),
    [eventId],
  );

  if (error) return <div className="alert-error">{error}</div>;
  if (loading || !event) return <p className="text-sm text-slate-500">{t("event.loading")}</p>;

  return (
    <div className="space-y-5">
      <header>
        {event.cover_image_url && (
          <img src={event.cover_image_url} alt="" className="mb-4 h-56 w-full rounded-xl object-cover" />
        )}
        <h1 className="text-3xl font-bold">{event.title}</h1>
        <p className="mt-1 text-slate-600">
          {formatDate(event.starts_at)} – {formatDate(event.ends_at)}
        </p>
        <p className="text-slate-600">
          {event.venue_name}, {event.venue_address}, {event.city}
        </p>
        {event.status !== "published" && (
          <p className="mt-2 inline-block rounded-full bg-amber-100 px-3 py-1 text-sm font-medium text-amber-800">
            {t(`eventStatus.${event.status}`)}
          </p>
        )}
        {event.description && <p className="mt-4 whitespace-pre-line">{event.description}</p>}
      </header>

      {event.seating_mode === "reserved" ? <SeatPlan event={event} /> : <GeneralBooking event={event} />}
    </div>
  );
}