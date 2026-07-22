import { apiFetch, API_BASE_URL, ApiError } from "@/lib/api";

export type MaintenancePriority = "low" | "medium" | "high" | "urgent";
export type MaintenanceStatus = "open" | "in_progress" | "resolved" | "cancelled";

export interface MaintenanceInfo {
  id: string;
  property_address: string;
  title: string;
  description: string;
  priority: MaintenancePriority;
  status: MaintenanceStatus;
  image_urls: string[];
  reported_by: string;
  created_at: string;
}

export interface MaintenanceCreateBody {
  title: string;
  description: string;
  priority: MaintenancePriority;
}

export function createMaintenance(leaseId: string, body: MaintenanceCreateBody) {
  return apiFetch<MaintenanceInfo>(`/api/v1/me/leases/${leaseId}/maintenance`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function listLeaseMaintenance(leaseId: string) {
  return apiFetch<MaintenanceInfo[]>(`/api/v1/me/leases/${leaseId}/maintenance`);
}

export function cancelMaintenance(id: string) {
  return apiFetch<MaintenanceInfo>(`/api/v1/me/maintenance/${id}/cancel`, { method: "POST" });
}

export async function uploadMaintenanceImage(id: string, file: File): Promise<MaintenanceInfo> {
  const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(`${API_BASE_URL}/api/v1/me/maintenance/${id}/images`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new ApiError(response.status, body.detail ?? "Upload failed");
  }
  return response.json();
}

export function listMaintenance(status?: MaintenanceStatus) {
  const query = status ? `?status=${status}` : "";
  return apiFetch<MaintenanceInfo[]>(`/api/v1/maintenance${query}`);
}

export function getMaintenance(id: string) {
  return apiFetch<MaintenanceInfo>(`/api/v1/maintenance/${id}`);
}

export function updateMaintenance(
  id: string,
  body: { status?: MaintenanceStatus; priority?: MaintenancePriority },
) {
  return apiFetch<MaintenanceInfo>(`/api/v1/maintenance/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}
