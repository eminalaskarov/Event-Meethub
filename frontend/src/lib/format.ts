import i18n from "../i18n";

function locale(): string {
  return i18n.resolvedLanguage ?? "en";
}

export function formatMoney(cents: number, currency: string): string {
  return new Intl.NumberFormat(locale(), {
    style: "currency",
    currency: currency.trim(),
  }).format(cents / 100);
}

export function formatDate(value: string): string {
  return new Intl.DateTimeFormat(locale(), {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function formatDistance(meters: number | null | undefined): string {
  if (meters == null) return "";
  if (meters < 1000) {
    return i18n.t("format.distanceMeters", { value: Math.round(meters) });
  }
  const kilometers = new Intl.NumberFormat(locale(), { maximumFractionDigits: 1 }).format(
    meters / 1000,
  );
  return i18n.t("format.distanceKm", { value: kilometers });
}

interface SeatInfo {
  section: string | null;
  row_label: string | null;
  seat_number: number | null;
}

export function seatLabel(ticket: SeatInfo): string {
  if (!ticket.section) return i18n.t("format.generalAdmission");
  return i18n.t("format.seat", {
    section: ticket.section,
    row: ticket.row_label,
    seat: ticket.seat_number,
  });
}

export function seatShortLabel(seat: SeatInfo): string {
  return i18n.t("format.seatShort", {
    section: seat.section,
    row: seat.row_label,
    seat: seat.seat_number,
  });
}