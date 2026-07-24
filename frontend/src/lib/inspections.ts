import { apiFetch, API_BASE_URL } from "@/lib/api";
import { getAccessToken } from "@/lib/auth";

export type InspectionType = "move_in" | "move_out" | "routine";
export type InspectionStatus = "scheduled" | "completed";
export type InspectionCondition = "good" | "fair" | "poor";

export interface InspectionItemIn {
  area: string;
  condition: InspectionCondition;
  note?: string | null;
}

export interface InspectionItemInfo {
  id: string;
  area: string;
  condition: InspectionCondition;
  note: string | null;
}

export interface InspectionInfo {
  id: string;
  property_id: string;
  lease_id: string | null;
  type: InspectionType;
  status: InspectionStatus;
  scheduled_for: string;
  note: string | null;
  image_urls: string[];
  items: InspectionItemInfo[];
  created_at: string;
}

export interface InspectionInput {
  property_id: string;
  lease_id?: string | null;
  type: InspectionType;
  status?: InspectionStatus;
  scheduled_for: string;
  note?: string | null;
  items: InspectionItemIn[];
}

export interface InspectionUpdate {
  status?: InspectionStatus;
  note?: string | null;
  scheduled_for?: string;
  items?: InspectionItemIn[];
}

export function listInspections(propertyId?: string) {
  const suffix = propertyId ? `?property_id=${propertyId}` : "";
  return apiFetch<InspectionInfo[]>(`/api/v1/inspections${suffix}`);
}

export function createInspection(body: InspectionInput) {
  return apiFetch<InspectionInfo>("/api/v1/inspections", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateInspection(id: string, body: InspectionUpdate) {
  return apiFetch<InspectionInfo>(`/api/v1/inspections/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteInspection(id: string) {
  return apiFetch<void>(`/api/v1/inspections/${id}`, { method: "DELETE" });
}

export async function uploadInspectionImage(id: string, file: File) {
  const token = getAccessToken();
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(`${API_BASE_URL}/api/v1/inspections/${id}/images`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  });
  if (!response.ok) throw new Error("Upload failed");
  return (await response.json()) as InspectionInfo;
}

export function listMyInspections(leaseId: string) {
  return apiFetch<InspectionInfo[]>(`/api/v1/me/leases/${leaseId}/inspections`);
}
