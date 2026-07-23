import { apiFetch } from "@/lib/api";

export interface MonthPoint {
  month: string;
  income: number;
  expenses: number;
  net: number;
}

export interface CategoryTotal {
  category: string;
  total: number;
}

export interface PropertyPnl {
  property_id: string | null;
  address: string;
  income: number;
  expenses: number;
  net: number;
}

export interface MonthlyReport {
  months: MonthPoint[];
  by_category: CategoryTotal[];
  by_property: PropertyPnl[];
}

export function getMonthlyReport(months = 12) {
  return apiFetch<MonthlyReport>(`/api/v1/reports/monthly?months=${months}`);
}
