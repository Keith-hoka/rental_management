import { apiFetch, API_BASE_URL, ApiError } from "@/lib/api";

export type PropertyStatus = "vacant" | "occupied";
export type PropertyType = "apartment" | "house" | "condo" | "townhouse" | "other";

export interface ActiveLease {
  id: string;
  tenant_name: string;
  rent_amount: number;
  rent_frequency: "weekly" | "fortnightly" | "monthly";
  start_date: string;
  end_date: string;
}

export interface Property {
  id: string;
  organization_id: string;
  address: string;
  type: PropertyType;
  bedrooms: number;
  bathrooms: number;
  parking: number;
  description: string | null;
  status: PropertyStatus;
  image_urls: string[];
  active_lease: ActiveLease | null;
}

export interface PropertyInput {
  address: string;
  type: PropertyType;
  bedrooms: number;
  bathrooms: number;
  parking: number;
  description: string;
  image_urls: string[];
}

export function listProperties(params: { search?: string; status?: string } = {}) {
  const q = new URLSearchParams();
  if (params.search) q.set("search", params.search);
  if (params.status) q.set("status", params.status);
  const suffix = q.toString() ? `?${q.toString()}` : "";
  return apiFetch<Property[]>(`/api/v1/properties${suffix}`);
}

export function getProperty(id: string) {
  return apiFetch<Property>(`/api/v1/properties/${id}`);
}

export function createProperty(body: PropertyInput) {
  return apiFetch<Property>("/api/v1/properties", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateProperty(id: string, body: Partial<PropertyInput>) {
  return apiFetch<Property>(`/api/v1/properties/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteProperty(id: string) {
  return apiFetch<void>(`/api/v1/properties/${id}`, { method: "DELETE" });
}

export async function uploadPropertyImage(id: string, file: File): Promise<Property> {
  const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(`${API_BASE_URL}/api/v1/properties/${id}/images`, {
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

/** Resolve a stored image URL (relative /uploads/... or absolute) to a full src. */
export function imageSrc(url: string): string {
  return url.startsWith("/") ? `${API_BASE_URL}${url}` : url;
}
