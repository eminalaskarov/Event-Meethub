import { useEffect, useRef, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { api, errorMessage } from "../api/client";
import type { PlaceSuggestion, Venue } from "../api/types";

export default function NewVenuePage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const sessionToken = useRef(crypto.randomUUID());
  const [search, setSearch] = useState("");
  const [suggestions, setSuggestions] = useState<PlaceSuggestion[]>([]);
  const [form, setForm] = useState({
    name: "",
    address: "",
    city: "",
    country: "",
    latitude: "",
    longitude: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (search.trim().length < 3) {
      setSuggestions([]);
      return;
    }

    let cancelled = false;
    const timer = window.setTimeout(async () => {
      try {
        const query = new URLSearchParams({ input: search, session_token: sessionToken.current });
        const result = await api.get<PlaceSuggestion[]>(`/venues/google/autocomplete?${query}`);
        if (!cancelled) {
          setSuggestions(result);
          setError(null);
        }
      } catch (caught) {
        if (!cancelled) setError(errorMessage(caught));
      }
    }, 350);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [search]);

  const importPlace = async (placeId: string) => {
    setBusy(true);
    setError(null);
    try {
      await api.post<Venue>("/venues/google/import", {
        google_place_id: placeId,
        session_token: sessionToken.current,
      });
      navigate("/manage/events/new");
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.post<Venue>("/venues", {
        ...form,
        latitude: Number(form.latitude),
        longitude: Number(form.longitude),
      });
      navigate("/manage/events/new");
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  };

  const textFields = ["name", "address", "city", "country"] as const;

  return (
    <div className="mx-auto max-w-xl space-y-4">
      <h1 className="text-2xl font-bold">{t("manage.venueForm.title")}</h1>
      {error && <div className="alert-error">{error}</div>}

      <section className="card">
        <label className="label" htmlFor="place-search">{t("manage.venueForm.findWithGoogle")}</label>
        <input id="place-search" className="input" value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={t("manage.venueForm.searchPlaceholder")} />
        {suggestions.length > 0 && (
          <ul className="mt-2 divide-y divide-slate-100 rounded-lg border border-slate-200">
            {suggestions.map((place) => (
              <li key={place.google_place_id}>
                <button type="button" disabled={busy}
                  className="w-full px-3 py-2 text-left text-sm hover:bg-slate-50"
                  onClick={() => void importPlace(place.google_place_id)}>
                  <span className="font-medium">{place.main_text}</span>
                  <span className="block text-xs text-slate-500">{place.secondary_text}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <form onSubmit={(event) => void submit(event)} className="card space-y-3">
        <h2 className="font-semibold">{t("manage.venueForm.manualTitle")}</h2>
        {textFields.map((key) => (
          <div key={key}>
            <label className="label" htmlFor={key}>{t(`manage.venueForm.${key}`)}</label>
            <input id={key} className="input" required value={form[key]}
              onChange={(e) => setForm((current) => ({ ...current, [key]: e.target.value }))} />
          </div>
        ))}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label" htmlFor="latitude">{t("manage.venueForm.latitude")}</label>
            <input id="latitude" className="input" type="number" step="any" min={-90} max={90} required
              value={form.latitude}
              onChange={(e) => setForm((current) => ({ ...current, latitude: e.target.value }))} />
          </div>
          <div>
            <label className="label" htmlFor="longitude">{t("manage.venueForm.longitude")}</label>
            <input id="longitude" className="input" type="number" step="any" min={-180} max={180} required
              value={form.longitude}
              onChange={(e) => setForm((current) => ({ ...current, longitude: e.target.value }))} />
          </div>
        </div>
        <button className="btn-primary w-full" disabled={busy}>{t("manage.venueForm.create")}</button>
      </form>
    </div>
  );
}