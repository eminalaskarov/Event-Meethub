import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, errorMessage } from "../api/client";
import type { ScannerEvent, ScanResponse, ScanResult } from "../api/types";
import CameraScanner from "../components/CameraScanner";
import { useApi } from "../hooks/useApi";
import { formatDate, seatLabel } from "../lib/format";

const RESULT_STYLES: Record<ScanResult, string> = {
  accepted: "bg-emerald-600 text-white",
  already_used: "bg-amber-500 text-amber-950",
  cancelled: "bg-red-600 text-white",
  wrong_event: "bg-red-600 text-white",
  invalid: "bg-red-600 text-white",
};

const DUPLICATE_WINDOW_MS = 4000;

export default function ScannerPage() {
  const { t } = useTranslation();
  const events = useApi(() => api.get<ScannerEvent[]>("/tickets/scanner-events"), []);
  const [eventId, setEventId] = useState("");
  const [cameraOn, setCameraOn] = useState(false);
  const [manualPayload, setManualPayload] = useState("");
  const [result, setResult] = useState<ScanResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const busyRef = useRef(false);
  const lastCameraScan = useRef({ payload: "", at: 0 });

  useEffect(() => {
    if (!eventId && events.data?.length) setEventId(events.data[0].id);
  }, [eventId, events.data]);

  const submitScan = useCallback(
    async (payload: string) => {
      if (!eventId || busyRef.current) return;

      busyRef.current = true;
      setError(null);
      try {
        setResult(await api.post<ScanResponse>(`/events/${eventId}/scan`, { qr_payload: payload }));
      } catch (caught) {
        setResult(null);
        setError(errorMessage(caught));
      } finally {
        busyRef.current = false;
      }
    },
    [eventId],
  );

  const handleCameraDecode = useCallback(
    (payload: string) => {
      const now = Date.now();
      const last = lastCameraScan.current;
      if (last.payload === payload && now - last.at < DUPLICATE_WINDOW_MS) return;
      lastCameraScan.current = { payload, at: now };
      void submitScan(payload);
    },
    [submitScan],
  );

  const submitManual = (event: FormEvent) => {
    event.preventDefault();
    const payload = manualPayload.trim();
    if (payload) void submitScan(payload);
  };

  return (
    <div className="mx-auto max-w-md space-y-4">
      <h1 className="text-2xl font-bold">{t("scanner.title")}</h1>
      {events.error && <div className="alert-error">{events.error}</div>}

      {events.data?.length === 0 ? (
        <p className="card text-sm text-slate-600">{t("scanner.notAssigned")}</p>
      ) : (
        <>
          <div>
            <label className="label" htmlFor="scan-event">{t("scanner.event")}</label>
            <select id="scan-event" className="input" value={eventId}
              onChange={(e) => {
                setEventId(e.target.value);
                setResult(null);
              }}>
              {events.data?.map((event) => (
                <option key={event.id} value={event.id}>
                  {event.title} · {formatDate(event.starts_at)}
                </option>
              ))}
            </select>
          </div>

          <button type="button" className={cameraOn ? "btn-secondary w-full" : "btn-primary w-full"}
            disabled={!eventId} onClick={() => setCameraOn((value) => !value)}>
            {cameraOn ? t("scanner.stopCamera") : t("scanner.startCamera")}
          </button>

          {cameraOn && <CameraScanner onDecode={handleCameraDecode} />}

          {error && <div className="alert-error">{error}</div>}

          {result && (
            <section className={`rounded-xl p-6 text-center ${RESULT_STYLES[result.result]}`} aria-live="assertive">
              <p className="text-3xl font-bold">{t(`scanner.results.${result.result}`)}</p>
              {result.ticket && (
                <div className="mt-3 text-sm">
                  <p className="text-lg font-semibold">{result.ticket.holder_name}</p>
                  <p>{result.ticket.tier_name}</p>
                  <p>{seatLabel(result.ticket)}</p>
                  {result.ticket.checked_in_at && (
                    <p className="mt-1">
                      {t("scanner.checkedIn", { time: formatDate(result.ticket.checked_in_at) })}
                    </p>
                  )}
                </div>
              )}
            </section>
          )}

          <form onSubmit={submitManual} className="card space-y-3">
            <label className="label !mb-0" htmlFor="manual-qr">{t("scanner.manualLabel")}</label>
            <textarea id="manual-qr" className="input" rows={2} value={manualPayload}
              onChange={(e) => setManualPayload(e.target.value)} />
            <button className="btn-secondary w-full" disabled={!eventId || !manualPayload.trim()}>
              {t("scanner.validate")}
            </button>
          </form>
        </>
      )}
    </div>
  );
}