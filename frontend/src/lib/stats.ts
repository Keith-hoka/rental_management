import { apiFetch } from "@/lib/api";

export interface MonthlyIncome {
  month: string;
  amount: number;
}

export interface OccupancyPoint {
  month: string;
  occupied: number;
  total: number;
  rate: number;
}

export interface MaintenanceStatusCount {
  status: string;
  count: number;
}

export interface DashboardStats {
  outstanding: number;
  overdue: number;
  collected_this_month: number;
  properties_total: number;
  properties_occupied: number;
  active_leases: number;
  tenants: number;
  maintenance_open: number;
  monthly_income: MonthlyIncome[];
  occupancy: OccupancyPoint[];
  maintenance_by_status: MaintenanceStatusCount[];
}

export function getDashboardStats() {
  return apiFetch<DashboardStats>("/api/v1/stats");
}
