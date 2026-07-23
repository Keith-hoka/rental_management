import { apiFetch } from "@/lib/api";

export type CalendarKind = "lease_start" | "lease_end" | "rent_due" | "maintenance" | "event";

export interface CalendarEntry {
  kind: CalendarKind;
  title: string;
  all_day: boolean;
  date: string | null;
  start_at: string | null;
  end_at: string | null;
  link: string | null;
  event_id: string | null;
  description: string | null;
  property_id: string | null;
}

export interface CalendarEventInput {
  title: string;
  description?: string | null;
  start_at: string;
  end_at: string;
  property_id?: string | null;
}

export interface CalendarEventInfo extends CalendarEventInput {
  id: string;
  created_at: string;
}

export function listCalendar(start: string, end: string) {
  return apiFetch<CalendarEntry[]>(`/api/v1/calendar?start=${start}&end=${end}`);
}

export function createEvent(body: CalendarEventInput) {
  return apiFetch<CalendarEventInfo>("/api/v1/calendar/events", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateEvent(id: string, body: Partial<CalendarEventInput>) {
  return apiFetch<CalendarEventInfo>(`/api/v1/calendar/events/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteEvent(id: string) {
  return apiFetch<void>(`/api/v1/calendar/events/${id}`, { method: "DELETE" });
}
