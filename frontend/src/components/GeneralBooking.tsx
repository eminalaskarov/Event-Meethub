import { useEffect, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router-dom";

import { api, errorMessage } from "../api/client";
import type { EventItem, Order, Tier } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { useApi } from "../hooks/useApi";
import { useSeatMap } from "../hooks/useSeatMap";
import { formatMoney } from "../lib/format";

export default function GeneralBooking({ event }: { event: EventItem }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const { map, status, refresh } = useSeatMap(event.id);
  const tiers = useApi(() => api.get<Tier[]>(`/events/${event.id}/tiers`), [event.id]);
  const [tierId, setTierId] = useState("");
  const [quantity, setQuantity] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!tierId && tiers.data?.length) setTierId(tiers.data[0].id);
  }, [tierId, tiers.data]);

  const remaining = map?.tickets_remaining ?? 0;
  const maxQuantity = Math.max(1, Math.min(event.max_tickets_per_order, remaining));
  const selectedTier = tiers.data?.find((tier) => tier.id === tierId);
  const noTiers = !tiers.loading && tiers.data?.length === 0;

  const submit = async (formEvent: FormEvent) => {
    formEvent.preventDefault();
    if (!user) {
      navigate("/login", { state: { from: location.pathname } });
      return;
    }

    setBusy(true);
    setError(null);
    try {
      await api.post<Order>(`/events/${event.id}/book-general`, { tier_id: tierId, quantity });
      navigate("/wallet");
    } catch (caught) {
      setError(errorMessage(caught));
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={(formEvent) => void submit(formEvent)} className="card max-w-md space-y-4">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">{t("generalBooking.title")}</h2>
        <span className="text-sm text-slate-600" aria-live="polite">
          {status === "live" ? t("common.live") : t("generalBooking.updating")} ·{" "}
          {t("generalBooking.left", { count: remaining })}
        </span>
      </div>

      {(error || tiers.error) && <div className="alert-error">{error ?? tiers.error}</div>}

      {noTiers ? (
        <p className="text-sm text-slate-600">{t("generalBooking.noTiers")}</p>
      ) : (
        <>
          <div>
            <label className="label" htmlFor="tier">{t("generalBooking.ticketType")}</label>
            <select id="tier" className="input" value={tierId} onChange={(e) => setTierId(e.target.value)}>
              {tiers.data?.map((tier) => (
                <option key={tier.id} value={tier.id}>
                  {tier.name} — {formatMoney(tier.price_cents, event.currency)}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="label" htmlFor="quantity">{t("generalBooking.quantity")}</label>
            <input
              id="quantity"
              className="input"
              type="number"
              min={1}
              max={maxQuantity}
              value={quantity}
              onChange={(e) => setQuantity(Number(e.target.value))}
            />
          </div>

          {selectedTier && (
            <p className="font-semibold">
              {t("generalBooking.totalAmount", {
                amount: formatMoney(selectedTier.price_cents * quantity, event.currency),
              })}
            </p>
          )}

          <button
            className="btn-primary w-full"
            disabled={busy || remaining === 0 || !tierId || event.status !== "published"}
          >
            {remaining === 0
              ? t("generalBooking.soldOut")
              : busy
                ? t("generalBooking.booking")
                : t("generalBooking.book")}
          </button>
          <p className="text-xs text-slate-500">{t("common.demoCheckout")}</p>
        </>
      )}
    </form>
  );
}