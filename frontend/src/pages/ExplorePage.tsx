import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import type { EventItem, Venue } from "../api/types";
import EventMap, { type LatLng } from "../components/EventMap";
import { useApi } from "../hooks/useApi";
import { formatDate, formatDistance } from "../lib/format";

const DEFAULT_CENTER: LatLng = { lat: 40.4093, lng: 49.8671 };
const RADIUS_OPTIONS = [5, 10, 25, 50, 100];

function roundCoordinate(value: number): number {
  return Math.round(value * 1000) / 1000;
}

export default function ExplorePage() {
  const { t } = useTranslation();
  const [center, setCenter] = useState(DEFAULT_CENTER);
  const [flyTo, setFlyTo] = useState<LatLng | null>(null);
  const [radiusKm, setRadiusKm] = useState(25);
  const [locationError, setLocationError] = useState(false);

  const nearby = useApi(async () => {
    const query = `lat=${center.lat}&lng=${center.lng}&radius_km=${radiusKm}&limit=100`;
    const [events, venues] = await Promise.all([
      api.get<EventItem[]>(`/events/nearby?${query}`),
      api.get<Venue[]>(`/venues/nearby?${query}`),
    ]);
    return { events, venues };
  }, [center.lat, center.lng, radiusKm]);

  const updateCenter = (next: LatLng) => {
    const rounded = { lat: roundCoordinate(next.lat), lng: roundCoordinate(next.lng) };
    setCenter((current) =>
      current.lat === rounded.lat && current.lng === rounded.lng ? current : rounded,
    );
  };

  const useMyLocation = () => {
    setLocationError(false);
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        const target = { lat: coords.latitude, lng: coords.longitude };
        setFlyTo(target);
        updateCenter(target);
      },
      () => setLocationError(true),
    );
  };

  const events = nearby.data?.events ?? [];
  const venues = nearby.data?.venues ?? [];
  const pageError = nearby.error ?? (locationError ? t("explore.locationError") : null);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">{t("explore.title")}</h1>
          <p className="text-sm text-slate-600">{t("explore.subtitle")}</p>
        </div>
        <div className="flex items-end gap-2">
          <div>
            <label className="label" htmlFor="radius">{t("explore.radius")}</label>
            <select id="radius" className="input" value={radiusKm}
              onChange={(e) => setRadiusKm(Number(e.target.value))}>
              {RADIUS_OPTIONS.map((km) => (
                <option key={km} value={km}>{t("explore.radiusOption", { km })}</option>
              ))}
            </select>
          </div>
          <button type="button" className="btn-secondary" onClick={useMyLocation}>
            {t("explore.useMyLocation")}
          </button>
        </div>
      </div>

      {pageError && <div className="alert-error">{pageError}</div>}

      <div className="h-[55vh] min-h-80 overflow-hidden rounded-xl border border-slate-200">
        <EventMap
          initialCenter={DEFAULT_CENTER}
          flyTo={flyTo}
          events={events}
          venues={venues}
          onCenterChange={updateCenter}
        />
      </div>

      <section>
        <h2 className="mb-3 text-lg font-semibold">
          {t("explore.upcomingEvents", { count: events.length })}
        </h2>
        {!nearby.loading && events.length === 0 && (
          <p className="text-sm text-slate-500">{t("explore.noEvents")}</p>
        )}
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {events.map((event) => (
            <Link key={event.id} to={`/events/${event.id}`} className="card hover:border-indigo-300">
              <h3 className="font-semibold">{event.title}</h3>
              <p className="mt-1 text-sm text-slate-600">{formatDate(event.starts_at)}</p>
              <p className="text-sm text-slate-600">{event.venue_name}, {event.city}</p>
              <p className="mt-2 text-xs font-medium text-indigo-700">
                {formatDistance(event.distance_m)}
              </p>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}