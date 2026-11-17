export type Role = "attendee" | "organizer" | "admin";
export type SeatingMode = "reserved" | "general";
export type EventStatus = "draft" | "published" | "cancelled" | "completed";
export type SeatStatus = "available" | "held" | "booked" | "blocked";
export type TicketStatus = "valid" | "used" | "cancelled";
export type ScanResult = "accepted" | "already_used" | "cancelled" | "wrong_event" | "invalid";

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  is_active: boolean;
  created_at: string;
}

export interface Venue {
  id: string;
  name: string;
  address: string;
  city: string;
  country: string;
  latitude: number;
  longitude: number;
  google_place_id: string | null;
  created_by: string;
  distance_m?: number;
}

export interface EventItem {
  id: string;
  organizer_id: string;
  venue_id: string;
  title: string;
  description: string | null;
  cover_image_url: string | null;
  starts_at: string;
  ends_at: string;
  status: EventStatus;
  seating_mode: SeatingMode;
  capacity: number | null;
  currency: string;
  max_tickets_per_order: number;
  venue_name: string;
  venue_address: string;
  city: string;
  country: string;
  latitude: number;
  longitude: number;
  distance_m: number | null;
}

export interface Tier {
  id: string;
  event_id: string;
  name: string;
  price_cents: number;
}

export interface VenueSeat {
  id: string;
  section: string;
  row_label: string;
  seat_number: number;
  pos_x: number | null;
  pos_y: number | null;
}

export interface LiveSeat {
  event_seat_id: string;
  seat_id: string;
  section: string;
  row_label: string;
  seat_number: number;
  pos_x: number | null;
  pos_y: number | null;
  tier_id: string;
  tier_name: string;
  price_cents: number;
  status: SeatStatus;
  held_by_me: boolean;
  hold_expires_at: string | null;
}

export interface SeatMap {
  event_id: string;
  seating_mode: SeatingMode;
  capacity: number | null;
  tickets_remaining: number;
  server_time: string;
  seats: LiveSeat[];
}

export interface HoldResponse {
  event_id: string;
  event_seat_ids: string[];
  hold_expires_at: string;
}

export interface ReleaseResponse {
  event_id: string;
  released_event_seat_ids: string[];
}

export interface Order {
  id: string;
  event_id: string;
  status: string;
  total_cents: number;
  currency: string;
  tickets: { id: string }[];
}

export interface WalletTicket {
  ticket_id: string;
  event_id: string;
  event_title: string;
  starts_at: string;
  venue_name: string;
  city: string;
  tier_name: string;
  section: string | null;
  row_label: string | null;
  seat_number: number | null;
  price_cents: number;
  currency: string;
  status: TicketStatus;
  checked_in_at: string | null;
}

export interface TicketQr {
  ticket_id: string;
  event_id: string;
  status: "valid" | "used";
  qr_payload: string;
}

export interface ScannerEvent {
  id: string;
  title: string;
  starts_at: string;
  venue_name: string;
}

export interface ScanResponse {
  result: ScanResult;
  admitted: boolean;
  scanned_at: string;
  ticket: {
    ticket_id: string;
    holder_name: string;
    tier_name: string;
    section: string | null;
    row_label: string | null;
    seat_number: number | null;
    status: TicketStatus;
    checked_in_at: string | null;
  } | null;
}

export interface PlaceSuggestion {
  google_place_id: string;
  description: string;
  main_text: string;
  secondary_text: string;
}

export type RealtimeMessage =
  | { type: "connected"; event_id: string; server_time: string }
  | { type: "resync"; event_id: string; server_time: string }
  | {
      type: "availability.updated";
      event_id: string;
      tickets_remaining: number;
      server_time: string;
    }
  | {
      type: "seats.updated";
      event_id: string;
      reason: string;
      server_time: string;
      seats: {
        event_seat_id: string;
        status: SeatStatus;
        hold_expires_at: string | null;
      }[];
    };