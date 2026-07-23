"use client";

import { useEffect, useState } from "react";
import {
  createExpense,
  deleteExpense,
  listExpenses,
  type ExpenseCategory,
  type ExpenseInfo,
} from "@/lib/expenses";
import { listProperties, type Property } from "@/lib/properties";
import { AppShell } from "@/components/app-shell";
import { useShell } from "@/components/use-shell";
import { Badge, Button, Card, ConfirmDialog, Input, PageHeader, Select } from "@/components/ui";

const CATEGORIES: ExpenseCategory[] = [
  "maintenance",
  "insurance",
  "tax",
  "utilities",
  "management",
  "other",
];

export default function ExpensesPage() {
  const { me, unread, logOut } = useShell();
  const [expenses, setExpenses] = useState<ExpenseInfo[]>([]);
  const [properties, setProperties] = useState<Property[]>([]);
  const [amount, setAmount] = useState("");
  const [spentOn, setSpentOn] = useState(() => new Date().toISOString().slice(0, 10));
  const [category, setCategory] = useState<ExpenseCategory>("maintenance");
  const [note, setNote] = useState("");
  const [propertyId, setPropertyId] = useState("");
  const [deletingId, setDeletingId] = useState<string | null>(null);

  useEffect(() => {
    if (!me) return;
    let active = true;
    listExpenses()
      .then((e) => active && setExpenses(e))
      .catch(() => active && setExpenses([]));
    listProperties()
      .then((p) => active && setProperties(p))
      .catch(() => active && setProperties([]));
    return () => {
      active = false;
    };
  }, [me]);

  if (!me) return null;

  const addressOf = (id: string | null) =>
    id ? (properties.find((p) => p.id === id)?.address ?? "") : "";

  async function refresh() {
    setExpenses(await listExpenses());
  }

  async function onAdd(e: React.FormEvent) {
    e.preventDefault();
    await createExpense({
      amount,
      spent_on: spentOn,
      category,
      note: note || null,
      property_id: propertyId || null,
    });
    setAmount("");
    setNote("");
    setPropertyId("");
    await refresh();
  }

  async function onDelete(id: string) {
    setDeletingId(null);
    await deleteExpense(id);
    await refresh();
  }

  return (
    <AppShell me={me} unread={unread} onLogOut={logOut}>
      <PageHeader title="Expenses" />
      <Card title="Record an expense">
        <form onSubmit={onAdd} className="flex flex-wrap items-end gap-2">
          <Input
            type="number"
            min="0.01"
            step="0.01"
            required
            placeholder="Amount"
            aria-label="Amount"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            className="w-28"
          />
          <Input
            type="date"
            required
            aria-label="Date"
            value={spentOn}
            onChange={(e) => setSpentOn(e.target.value)}
            className="w-40"
          />
          <Select
            aria-label="Category"
            value={category}
            onChange={(e) => setCategory(e.target.value as ExpenseCategory)}
            className="w-40"
          >
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </Select>
          <Select
            aria-label="Property"
            value={propertyId}
            onChange={(e) => setPropertyId(e.target.value)}
            className="w-48"
          >
            <option value="">No property</option>
            {properties.map((p) => (
              <option key={p.id} value={p.id}>
                {p.address}
              </option>
            ))}
          </Select>
          <Input
            type="text"
            placeholder="Note (optional)"
            aria-label="Note"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            className="flex-1"
          />
          <Button type="submit">Add expense</Button>
        </form>
      </Card>

      <Card title="All expenses" className="mt-5">
        {expenses.length === 0 ? (
          <p className="text-sm text-muted">No expenses yet.</p>
        ) : (
          <ul className="space-y-1 text-sm text-text">
            {expenses.map((x) => (
              <li key={x.id} className="flex items-center justify-between gap-2">
                <span>
                  {x.spent_on} · <Badge tone="neutral">{x.category}</Badge> ${x.amount}
                  {x.property_id ? ` · ${addressOf(x.property_id)}` : ""}
                  {x.note ? ` · ${x.note}` : ""}
                </span>
                <Button
                  variant="danger"
                  size="sm"
                  aria-label={`Delete expense of $${x.amount} on ${x.spent_on}`}
                  onClick={() => setDeletingId(x.id)}
                >
                  Delete
                </Button>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <ConfirmDialog
        open={deletingId !== null}
        label="Delete expense"
        message="Delete this expense? This cannot be undone."
        confirmLabel="Yes, delete"
        onConfirm={() => deletingId && onDelete(deletingId)}
        onCancel={() => setDeletingId(null)}
      />
    </AppShell>
  );
}
