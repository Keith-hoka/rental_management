import { apiFetch, API_BASE_URL } from "@/lib/api";
import { getAccessToken } from "@/lib/auth";

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

export async function exportPayments(start?: string, end?: string): Promise<Blob> {
  const params = new URLSearchParams();
  if (start) params.set("start", start);
  if (end) params.set("end", end);
  const query = params.toString();
  // Not apiFetch: that assumes a JSON body. The auth header is still required,
  // so a plain link would 401.
  const response = await fetch(
    `${API_BASE_URL}/api/v1/payments/export${query ? `?${query}` : ""}`,
    {
      cache: "no-store",
      headers: { Authorization: `Bearer ${getAccessToken() ?? ""}` },
    },
  );
  if (!response.ok) throw new Error("Export failed");
  return response.blob();
}
