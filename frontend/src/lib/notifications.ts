import { apiFetch } from "@/lib/api";

export interface NotificationInfo {
  id: string;
  category: string;
  title: string;
  body: string;
  link: string | null;
  created_at: string;
  read_at: string | null;
}

export interface UnreadCount {
  count: number;
}

export function listNotifications(unreadOnly?: boolean) {
  const query = unreadOnly ? "?unread=true" : "";
  return apiFetch<NotificationInfo[]>(`/api/v1/me/notifications${query}`);
}

export function getUnreadCount() {
  return apiFetch<UnreadCount>("/api/v1/me/notifications/unread_count");
}

export function markRead(id: string) {
  return apiFetch<NotificationInfo>(`/api/v1/me/notifications/${id}/read`, { method: "POST" });
}

export function markAllRead() {
  return apiFetch<UnreadCount>("/api/v1/me/notifications/read_all", { method: "POST" });
}

export function deleteNotification(id: string) {
  return apiFetch<void>(`/api/v1/me/notifications/${id}`, { method: "DELETE" });
}
