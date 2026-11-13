import { QRCodeSVG } from "qrcode.react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import type { TicketQr, WalletTicket } from "../api/types";
import { useApi } from "../hooks/useApi";
import { formatDate, formatMoney, seatLabel } from "../lib/format";

function TicketCode({ ticketId }: { ticketId: string }) {
  const { t } = useTranslation();
  const { data, loading, error } = useApi(
    () => api.get<TicketQr>(`/tickets/${ticketId}/qr`),
    [ticketId],
  );

  if (error) return <div className="alert-error mt-4">{error}</div>;
  if (loading || !data) {
    return <p className="mt-4 text-sm text-slate-500">{t("wallet.loadingQr")}</p>;
  }

  return (
    <div className="mt-4 flex justify-center rounded-lg bg-white p-3">
      <QRCodeSVG value={data.qr_payload} size={232} level="M" marginSize={2} title={t("wallet.qrTitle")} />
    </div>
  );
}

const statusStyles = {
  valid: "bg-emerald-100 text-emerald-800",
  used: "bg-slate-200 text-slate-700",
  cancelled: "bg-red-100 text-red-800",
};

export default function WalletPage() {
  const { t } = useTranslation();
  const { data, loading, error } = useApi(() => api.get<WalletTicket[]>("/tickets/mine"), []);
  const [openTicket, setOpenTicket] = useState<string | null>(null);

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">{t("wallet.title")}</h1>
      {error && <div className="alert-error">{error}</div>}
      {loading && <p className="text-sm text-slate-500">{t("wallet.loading")}</p>}
      {data?.length === 0 && <p className="text-sm text-slate-500">{t("wallet.empty")}</p>}

      <div className="grid gap-4 md:grid-cols-2">
        {data?.map((ticket) => (
          <article key={ticket.ticket_id} className="card">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="font-semibold">{ticket.event_title}</h2>
                <p className="text-sm text-slate-600">{formatDate(ticket.starts_at)}</p>
                <p className="text-sm text-slate-600">{ticket.venue_name}, {ticket.city}</p>
              </div>
              <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${statusStyles[ticket.status]}`}>
                {t(`ticketStatus.${ticket.status}`)}
              </span>
            </div>
            <p className="mt-3 text-sm">{seatLabel(ticket)}</p>
            <p className="text-sm text-slate-600">
              {ticket.tier_name} · {formatMoney(ticket.price_cents, ticket.currency)}
            </p>

            {ticket.status !== "cancelled" && (
              <button
                type="button"
                className="btn-secondary mt-4 w-full"
                aria-expanded={openTicket === ticket.ticket_id}
                onClick={() =>
                  setOpenTicket((current) => (current === ticket.ticket_id ? null : ticket.ticket_id))
                }
              >
                {openTicket === ticket.ticket_id ? t("wallet.hideQr") : t("wallet.showQr")}
              </button>
            )}
            {openTicket === ticket.ticket_id && <TicketCode ticketId={ticket.ticket_id} />}
          </article>
        ))}
      </div>
    </div>
  );
}