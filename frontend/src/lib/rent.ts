import { apiFetch } from "@/lib/api";
import type { ChargeInfo } from "@/lib/charges";

export interface LeaseChargeGroup {
  lease_id: string;
  property_address: string;
  tenant_name: string;
  total: number;
  oldest_due: string;
  charges: ChargeInfo[];
}

export interface RentSummary {
  overdue: LeaseChargeGroup[];
  upcoming: LeaseChargeGroup[];
}

export function getRentSummary() {
  return apiFetch<RentSummary>("/api/v1/rent/summary");
}
