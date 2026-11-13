import {
  AdvancedMarker,
  APIProvider,
  InfoWindow,
  Map as GoogleMap,
  Pin,
  useMap,
} from "@vis.gl/react-google-maps";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import type { EventItem, Venue } from "../api/types";
import { formatDate } from "../lib/format";

export interface LatLng {
  lat: number;
  lng: number;
}

interface MapPlace {
  id: string;
  name: string;
  position: LatLng;
  events: EventItem[];
}

interface EventMapProps {
  initialCenter: LatLng;
  flyTo: LatLng | null;
  events: EventItem[];
  venues: Venue[];
  onCenterChange: (center: LatLng) => void;
}

const API_KEY = import.meta.env.VITE_GOOGLE_MAPS_API_KEY ?? "";
const MAP_ID = import.meta.env.VITE_GOOGLE_MAPS_MAP_ID || "DEMO_MAP_ID";

function FlyTo({ target }: { target: LatLng | null }) {
  const map = useMap();

  useEffect(() => {
    if (map && target) map.panTo(target);
  }, [map, target]);

  return null;
}

export default function EventMap({
  initialCenter,
  flyTo,
  events,
  venues,
  onCenterChange,
}: EventMapProps) {
  const { t } = useTranslation();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const places = useMemo(() => {
    const result = new Map<string, MapPlace>();

    for (const venue of venues) {
      result.set(venue.id, {
        id: venue.id,
        name: venue.name,
        position: { lat: venue.latitude, lng: venue.longitude },
        events: [],
      });
    }

    for (const event of events) {
      const place = result.get(event.venue_id) ?? {
        id: event.venue_id,
        name: event.venue_name,
        position: { lat: event.latitude, lng: event.longitude },
        events: [],
      };
      place.events.push(event);
      result.set(event.venue_id, place);
    }

    return [...result.values()];
  }, [events, venues]);

  const selected = places.find((place) => place.id === selectedId) ?? null;

  if (!API_KEY) {
    return (
      <div className="flex h-full items-center justify-center bg-slate-100 p-6 text-center text-sm text-slate-600">
        {t("map.missingKey")}
      </div>
    );
  }

  return (
    <APIProvider apiKey={API_KEY}>
      <GoogleMap
        className="h-full w-full"
        defaultCenter={initialCenter}
        defaultZoom={12}
        mapId={MAP_ID}
        gestureHandling="greedy"
        onClick={() => setSelectedId(null)}
        onIdle={(event) => {
          const center = event.map.getCenter();
          if (center) onCenterChange({ lat: center.lat(), lng: center.lng() });
        }}
      >
        <FlyTo target={flyTo} />

        {places.map((place) => (
          <AdvancedMarker
            key={place.id}
            position={place.position}
            title={place.name}
            onClick={() => setSelectedId(place.id)}
          >
            <Pin
              background={place.events.length ? "#4f46e5" : "#94a3b8"}
              borderColor={place.events.length ? "#312e81" : "#475569"}
              glyphColor="#ffffff"
            />
          </AdvancedMarker>
        ))}

        {selected && (
          <InfoWindow
            position={selected.position}
            pixelOffset={[0, -36]}
            onCloseClick={() => setSelectedId(null)}
          >
            <div className="max-w-56 text-slate-900">
              <p className="font-semibold">{selected.name}</p>
              {selected.events.length === 0 && (
                <p className="mt-1 text-xs text-slate-500">{t("map.noUpcomingEvents")}</p>
              )}
              <ul className="mt-1 space-y-1">
                {selected.events.map((event) => (
                  <li key={event.id}>
                    <Link className="text-sm text-indigo-700 underline" to={`/events/${event.id}`}>
                      {event.title}
                    </Link>
                    <p className="text-xs text-slate-500">{formatDate(event.starts_at)}</p>
                  </li>
                ))}
              </ul>
            </div>
          </InfoWindow>
        )}
      </GoogleMap>
    </APIProvider>
  );
}