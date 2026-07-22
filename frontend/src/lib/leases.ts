import { apiFetch } from "@/lib/api";

export type LeaseFrequency = "weekly" | "fortnightly" | "monthly";

export interface CoTenant {
  name: string;
  email: string;
  phone: string;
}

export interface Lease {
  id: string;
  property_id: string;
  tenant_name: string;
  tenant_email: string;
  tenant_phone: string | null;
  co_tenants: CoTenant[];
  rent_amount: number;
  rent_frequency: LeaseFrequency;
  bond_amount: number | null;
  notice_period_days: number | null;
  start_date: string;
  end_date: string;
  created_at: string;
  renewed_from_id: string | null;
  // Only GET /leases/{id} fills this in; it is null on the list endpoints.
  renewed_to_id: string | null;
}

export interface LeaseInput {
  tenant_name: string;
  tenant_email: string;
  tenant_phone: string;
  co_tenants: CoTenant[];
  rent_amount: number;
  rent_frequency: LeaseFrequency;
  bond_amount: number | null;
  notice_period_days: number | null;
  start_date: string;
  end_date: string;
}

export interface LeaseRenewInput {
  end_date: string;
  start_date?: string;
  rent_amount?: number;
  rent_frequency?: LeaseFrequency;
  bond_amount?: number | null;
  notice_period_days?: number | null;
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

export function renewLease(id: string, input: LeaseRenewInput) {
  return apiFetch<Lease>(`/api/v1/leases/${id}/renew`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function deleteLease(id: string) {
  return apiFetch<void>(`/api/v1/leases/${id}`, { method: "DELETE" });
}
