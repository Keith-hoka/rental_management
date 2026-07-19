import { apiFetch } from "@/lib/api";

export type PropertyStatus = "vacant" | "occupied";
export type PropertyType = "apartment" | "house" | "condo" | "townhouse" | "other";

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
}

export interface PropertyInput {
  address: string;
  type: PropertyType;
  bedrooms: number;
  bathrooms: number;
  parking: number;
  description: string;
  status: PropertyStatus;
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
