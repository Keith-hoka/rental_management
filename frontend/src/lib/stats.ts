import { apiFetch } from "@/lib/api";

export interface MonthlyIncome {
  month: string;
  amount: number;
}

export interface DashboardStats {
  outstanding: number;
  overdue: number;
  collected_this_month: number;
  properties_total: number;
  properties_occupied: number;
  active_leases: number;
  tenants: number;
  monthly_income: MonthlyIncome[];
}

export function getDashboardStats() {
  return apiFetch<DashboardStats>("/api/v1/stats");
}
