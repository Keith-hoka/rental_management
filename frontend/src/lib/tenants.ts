import { apiFetch } from "@/lib/api";

export interface LeaseTenantInfo {
  name: string;
  email: string;
}

export interface LeaseInvitationInfo {
  id: string;
  email: string;
}

export interface LeaseReminderInfo {
  threshold_days: number;
  sent_at: string;
}

export interface TenantLease {
  id: string;
  property_address: string;
  rent_amount: number;
  rent_frequency: "weekly" | "fortnightly" | "monthly";
  start_date: string;
  end_date: string;
  bond_amount: number | null;
  notice_period_days: number | null;
  state: "active" | "upcoming" | "ended";
  landlord_name: string;
  landlord_email: string;
  landlord_phone: string | null;
  outstanding: number;
  overdue_amount: number;
}

export function inviteTenant(leaseId: string, email: string) {
  return apiFetch<unknown>(`/api/v1/leases/${leaseId}/invite`, {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

export function listLeaseTenants(leaseId: string) {
  return apiFetch<LeaseTenantInfo[]>(`/api/v1/leases/${leaseId}/tenants`);
}

export function listLeaseInvitations(leaseId: string) {
  return apiFetch<LeaseInvitationInfo[]>(`/api/v1/leases/${leaseId}/invitations`);
}

export function revokeLeaseInvitation(leaseId: string, invitationId: string) {
  return apiFetch<void>(`/api/v1/leases/${leaseId}/invitations/${invitationId}`, {
    method: "DELETE",
  });
}

export function listLeaseReminders(leaseId: string) {
  return apiFetch<LeaseReminderInfo[]>(`/api/v1/leases/${leaseId}/reminders`);
}

export function listMyLeases() {
  return apiFetch<TenantLease[]>("/api/v1/me/leases");
}
