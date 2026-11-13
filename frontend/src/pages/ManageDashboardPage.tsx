import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import type { EventItem } from "../api/types";
import { useApi } from "../hooks/useApi";
import { formatDate } from "../lib/format";

export default function ManageDashboardPage() {
  const { t } = useTranslation();
  const { data, loading, error } = useApi(() => api.get<EventItem[]>("/events/mine?limit=100"), []);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold">{t("manage.dashboard.title")}</h1>
        <div className="flex gap-2">
          <Link className="btn-secondary" to="/manage/venues/new">{t("manage.dashboard.newVenue")}</Link>
          <Link className="btn-primary" to="/manage/events/new">{t("manage.dashboard.newEvent")}</Link>
        </div>
      </div>

      {error && <div className="alert-error">{error}</div>}
      {loading && <p className="text-sm text-slate-500">{t("manage.dashboard.loading")}</p>}
      {data?.length === 0 && <p className="text-sm text-slate-500">{t("manage.dashboard.empty")}</p>}

      <div className="grid gap-3 md:grid-cols-2">
        {data?.map((event) => (
          <Link key={event.id} to={`/manage/events/${event.id}`} className="card hover:border-indigo-300">
            <div className="flex items-start justify-between gap-3">
              <h2 className="font-semibold">{event.title}</h2>
              <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold">
                {t(`eventStatus.${event.status}`)}
              </span>
            </div>
            <p className="mt-1 text-sm text-slate-600">{formatDate(event.starts_at)}</p>
            <p className="text-sm text-slate-600">{event.venue_name}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}