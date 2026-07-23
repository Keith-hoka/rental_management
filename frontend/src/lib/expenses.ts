import { apiFetch } from "@/lib/api";

export type ExpenseCategory =
  | "maintenance"
  | "insurance"
  | "tax"
  | "utilities"
  | "management"
  | "other";

export interface ExpenseInfo {
  id: string;
  amount: string;
  spent_on: string;
  category: ExpenseCategory;
  note: string | null;
  property_id: string | null;
  created_at: string;
}

export interface ExpenseInput {
  amount: string;
  spent_on: string;
  category: ExpenseCategory;
  note?: string | null;
  property_id?: string | null;
}

export function listExpenses() {
  return apiFetch<ExpenseInfo[]>("/api/v1/expenses");
}

export function createExpense(body: ExpenseInput) {
  return apiFetch<ExpenseInfo>("/api/v1/expenses", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function deleteExpense(id: string) {
  return apiFetch<void>(`/api/v1/expenses/${id}`, { method: "DELETE" });
}
