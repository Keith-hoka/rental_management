import { apiFetch } from "@/lib/api";

export interface ChargeInfo {
  id: string;
  period_start: string;
  period_end: string;
  due_date: string;
  amount_due: number;
  amount_paid: number;
  status: "unpaid" | "partial" | "paid";
  overdue: boolean;
}

export function listLeaseCharges(leaseId: string) {
  return apiFetch<ChargeInfo[]>(`/api/v1/leases/${leaseId}/charges`);
}
