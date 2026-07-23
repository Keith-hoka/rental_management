"use client";

import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getMonthlyReport, type MonthlyReport } from "@/lib/reports";
import { AppShell } from "@/components/app-shell";
import { useShell } from "@/components/use-shell";
import { Card, EmptyState, PageHeader } from "@/components/ui";

function money(n: number): string {
  return `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function Net({ n }: { n: number }) {
  return <span className={n < 0 ? "text-danger" : "text-text"}>{money(n)}</span>;
}

export default function ReportsPage() {
  const { me, unread, logOut } = useShell();
  const [report, setReport] = useState<MonthlyReport | null>(null);

  useEffect(() => {
    if (!me) return;
    let active = true;
    getMonthlyReport(12)
      .then((r) => active && setReport(r))
      .catch(() => active && setReport(null));
    return () => {
      active = false;
    };
  }, [me]);

  if (!me) return null;

  return (
    <AppShell me={me} unread={unread} onLogOut={logOut}>
      <PageHeader title="Reports" />
      {!report ? (
        <EmptyState>Loading…</EmptyState>
      ) : (
        <div className="space-y-5">
          <Card title="Income vs expenses">
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={report.months}>
                <XAxis dataKey="month" stroke="var(--ink-muted)" fontSize={12} />
                <YAxis stroke="var(--ink-muted)" fontSize={12} />
                <Tooltip
                  cursor={{ fill: "var(--surface-2)" }}
                  contentStyle={{
                    background: "var(--surface)",
                    border: "1px solid var(--line)",
                    borderRadius: 12,
                    color: "var(--ink)",
                  }}
                />
                <Legend />
                <Bar dataKey="income" fill="var(--brand)" radius={[6, 6, 0, 0]} isAnimationActive={false} />
                <Bar
                  dataKey="expenses"
                  fill="var(--danger)"
                  radius={[6, 6, 0, 0]}
                  isAnimationActive={false}
                />
              </BarChart>
            </ResponsiveContainer>
          </Card>

          <Card title="Monthly profit and loss">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-left text-muted">
                    <th className="py-1 pr-4 font-medium">Month</th>
                    <th className="py-1 pr-4 text-right font-medium">Income</th>
                    <th className="py-1 pr-4 text-right font-medium">Expenses</th>
                    <th className="py-1 text-right font-medium">Net</th>
                  </tr>
                </thead>
                <tbody>
                  {report.months.map((m) => (
                    <tr key={m.month} className="border-b border-border/50">
                      <td className="py-1 pr-4 text-text">{m.month}</td>
                      <td className="py-1 pr-4 text-right text-text">{money(m.income)}</td>
                      <td className="py-1 pr-4 text-right text-text">{money(m.expenses)}</td>
                      <td className="py-1 text-right">
                        <Net n={m.net} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          <Card title="Expenses by category">
            {report.by_category.length === 0 ? (
              <p className="text-sm text-muted">No expenses in this period.</p>
            ) : (
              <ul className="space-y-1 text-sm text-text">
                {report.by_category.map((c) => (
                  <li key={c.category} className="flex justify-between">
                    <span className="capitalize">{c.category}</span>
                    <span>{money(c.total)}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="By property">
            {report.by_property.length === 0 ? (
              <p className="text-sm text-muted">No income or expenses in this period.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-left text-muted">
                      <th className="py-1 pr-4 font-medium">Property</th>
                      <th className="py-1 pr-4 text-right font-medium">Income</th>
                      <th className="py-1 pr-4 text-right font-medium">Expenses</th>
                      <th className="py-1 text-right font-medium">Net</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.by_property.map((p) => (
                      <tr key={p.property_id ?? "unassigned"} className="border-b border-border/50">
                        <td className="py-1 pr-4 text-text">{p.address}</td>
                        <td className="py-1 pr-4 text-right text-text">{money(p.income)}</td>
                        <td className="py-1 pr-4 text-right text-text">{money(p.expenses)}</td>
                        <td className="py-1 text-right">
                          <Net n={p.net} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
      )}
    </AppShell>
  );
}
