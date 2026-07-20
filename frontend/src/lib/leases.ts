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

export type LeaseState = "active" | "upcoming" | "ended";

export interface LeaseSummary {
  id: string;
  property_id: string;
  property_address: string;
  tenant_name: string;
  rent_amount: number;
  rent_frequency: LeaseFrequency;
  start_date: string;
  end_date: string;
  state: LeaseState;
}

export function listAllLeases() {
  return apiFetch<LeaseSummary[]>("/api/v1/leases");
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
