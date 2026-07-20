import { apiFetch } from "@/lib/api";

export type LeaseFrequency = "weekly" | "fortnightly" | "monthly";

export interface Lease {
  id: string;
  property_id: string;
  tenant_name: string;
  tenant_email: string;
  rent_amount: number;
  rent_frequency: LeaseFrequency;
  bond_amount: number | null;
  notice_period_days: number | null;
  start_date: string;
  end_date: string;
  created_at: string;
}

export interface LeaseInput {
  tenant_name: string;
  tenant_email: string;
  rent_amount: number;
  rent_frequency: LeaseFrequency;
  bond_amount: number | null;
  notice_period_days: number | null;
  start_date: string;
  end_date: string;
}

export function listLeases(propertyId: string) {
  return apiFetch<Lease[]>(`/api/v1/properties/${propertyId}/leases`);
}

export function createLease(propertyId: string, input: LeaseInput) {
  return apiFetch<Lease>(`/api/v1/properties/${propertyId}/leases`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function getLease(id: string) {
  return apiFetch<Lease>(`/api/v1/leases/${id}`);
}

export function updateLease(id: string, input: Partial<LeaseInput>) {
  return apiFetch<Lease>(`/api/v1/leases/${id}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export function deleteLease(id: string) {
  return apiFetch<void>(`/api/v1/leases/${id}`, { method: "DELETE" });
}
