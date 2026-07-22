import { apiFetch } from "@/lib/api";

export type PaymentMethod = "cash" | "bank_transfer" | "other";

export interface PaymentInfo {
  id: string;
  amount: number;
  paid_on: string;
  method: PaymentMethod;
  note: string | null;
}

export interface RecentPayment {
  id: string;
  amount: number;
  paid_on: string;
  method: PaymentMethod;
  property_address: string;
  tenant_name: string;
}

export interface BalanceInfo {
  outstanding: number;
  overdue_amount: number;
  credit: number;
}

export interface PaymentBody {
  amount: number;
  paid_on: string;
  method: PaymentMethod;
  note: string | null;
}

export function recordPayment(leaseId: string, body: PaymentBody) {
  return apiFetch<PaymentInfo>(`/api/v1/leases/${leaseId}/payments`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function listLeasePayments(leaseId: string) {
  return apiFetch<PaymentInfo[]>(`/api/v1/leases/${leaseId}/payments`);
}

export function deleteLeasePayment(leaseId: string, paymentId: string) {
  return apiFetch<void>(`/api/v1/leases/${leaseId}/payments/${paymentId}`, {
    method: "DELETE",
  });
}

export function listRecentPayments(limit = 8) {
  return apiFetch<RecentPayment[]>(`/api/v1/payments/recent?limit=${limit}`);
}

export function getLeaseBalance(leaseId: string) {
  return apiFetch<BalanceInfo>(`/api/v1/leases/${leaseId}/balance`);
}
