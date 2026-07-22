"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { apiFetch, API_BASE_URL } from "@/lib/api";
import { clearTokens, getAccessToken } from "@/lib/auth";
import { listMyLeases, type TenantLease } from "@/lib/tenants";
import { listMyLeaseCharges, type ChargeInfo } from "@/lib/charges";
import { getDashboardStats, type DashboardStats } from "@/lib/stats";
import { getUnreadCount } from "@/lib/notifications";
import {
  createMaintenance,
  listLeaseMaintenance,
  cancelMaintenance,
  uploadMaintenanceImage,
  type MaintenanceInfo,
  type MaintenancePriority,
} from "@/lib/maintenance";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AppShell } from "@/components/app-shell";
import { Badge, Card, EmptyState, PageHeader, StatCard } from "@/components/ui";
import { listProperties, type Property } from "@/lib/properties";
import { listRecentPayments, type RecentPayment } from "@/lib/payments";

interface Me {
  email: string;
  name: string;
  role: string;
}

export default function DashboardPage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [myLeases, setMyLeases] = useState<TenantLease[]>([]);
  const [chargesByLease, setChargesByLease] = useState<Record<string, ChargeInfo[]>>({});
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [maintByLease, setMaintByLease] = useState<Record<string, MaintenanceInfo[]>>({});
  const [issueTitle, setIssueTitle] = useState("");
  const [issueDesc, setIssueDesc] = useState("");
  const [issuePriority, setIssuePriority] = useState<MaintenancePriority>("medium");
  const [unread, setUnread] = useState(0);
  const [properties, setProperties] = useState<Property[]>([]);
  const [recent, setRecent] = useState<RecentPayment[]>([]);

  useEffect(() => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    let active = true;
    apiFetch<Me>("/api/v1/auth/me")
      .then((m) => {
        if (!active) return;
        setMe(m);
        // Its own catch: a failed count must never trigger the auth logout below.
        getUnreadCount()
          .then((u) => {
            if (active) setUnread(u.count);
          })
          .catch(() => {
            if (active) setUnread(0);
          });
        if (m.role === "tenant") {
          return listMyLeases().then(async (l) => {
            if (!active) return;
            setMyLeases(l);
            const entries = await Promise.all(
              l.map((lease) =>
                listMyLeaseCharges(lease.id)
                  .then((c) => [lease.id, c] as const)
                  .catch(() => [lease.id, []] as const),
              ),
            );
            if (active) setChargesByLease(Object.fromEntries(entries));
            const maint = await Promise.all(
              l.map((lease) =>
                listLeaseMaintenance(lease.id)
                  .then((m) => [lease.id, m] as const)
                  .catch(() => [lease.id, []] as const),
              ),
            );
            if (active) setMaintByLease(Object.fromEntries(maint));
          });
        }
        // Each manager panel catches its own failure so one bad response
        // cannot take down the whole dashboard.
        listProperties()
          .then((p) => active && setProperties(p))
          .catch(() => active && setProperties([]));
        listRecentPayments()
          .then((r) => active && setRecent(r))
          .catch(() => active && setRecent([]));
        return getDashboardStats()
          .then((s) => {
            if (active) setStats(s);
          })
          .catch(() => {
            if (active) setStats(null);
          });
      })
      .catch(() => {
        clearTokens();
        router.replace("/login");
      });
    return () => {
      active = false;
    };
  }, [router]);

  if (!me) return null;

  function logOut() {
    clearTokens();
    router.replace("/login");
  }

  async function refreshMaint(leaseId: string) {
    const m = await listLeaseMaintenance(leaseId);
    setMaintByLease((prev) => ({ ...prev, [leaseId]: m }));
  }

  async function reportIssue(leaseId: string, e: React.FormEvent) {
    e.preventDefault();
    await createMaintenance(leaseId, {
      title: issueTitle,
      description: issueDesc,
      priority: issuePriority,
    });
    setIssueTitle("");
    setIssueDesc("");
    setIssuePriority("medium");
    await refreshMaint(leaseId);
  }

  if (me.role === "tenant") {
    return (
      <main className="mx-auto max-w-lg p-8">
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <p data-testid="welcome" className="mt-2 text-gray-700">
          Welcome, {me.name} ({me.role})
        </p>
        <h2 className="mb-2 mt-6 font-semibold">Your lease</h2>
        <ul className="space-y-3">
          {myLeases.map((l) => (
            <li key={l.id} className="rounded border p-3 text-sm">
              <p className="font-medium text-gray-800">{l.property_address}</p>
              <p className="text-gray-700">
                ${l.rent_amount} / {l.rent_frequency} · {l.start_date} to {l.end_date} · {l.state}
              </p>
              {l.bond_amount != null && <p className="text-gray-600">Bond: ${l.bond_amount}</p>}
              {l.notice_period_days != null && (
                <p className="text-gray-600">Notice period: {l.notice_period_days} days</p>
              )}
              <p className="mt-1 text-gray-700">
                Landlord contact: {l.landlord_name} — {l.landlord_email}
                {l.landlord_phone ? ` — ${l.landlord_phone}` : ""}
              </p>
              <p className="mt-1 text-gray-700">
                Outstanding <span className="font-medium text-gray-800">${l.outstanding}</span>
                {" · "}Overdue{" "}
                <span className="font-medium text-red-600">${l.overdue_amount}</span>
              </p>
              {(chargesByLease[l.id]?.length ?? 0) > 0 && (
                <ul className="mt-2 space-y-1 text-gray-700">
                  {chargesByLease[l.id].map((c) => (
                    <li key={c.id} className="flex justify-between">
                      <span>
                        {c.period_start} – {c.period_end} · due {c.due_date}
                      </span>
                      <span>
                        ${c.amount_paid} / ${c.amount_due} · {c.overdue ? "Overdue" : c.status}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
              <div className="mt-3">
                <p className="font-medium text-gray-800">Maintenance</p>
                <form onSubmit={(e) => reportIssue(l.id, e)} className="mt-1 flex flex-wrap gap-2">
                  <input
                    required
                    placeholder="Issue title"
                    value={issueTitle}
                    onChange={(e) => setIssueTitle(e.target.value)}
                    className="w-40 rounded border px-2 py-1 text-sm"
                  />
                  <input
                    required
                    placeholder="Description"
                    value={issueDesc}
                    onChange={(e) => setIssueDesc(e.target.value)}
                    className="flex-1 rounded border px-2 py-1 text-sm"
                  />
                  <select
                    aria-label="Priority"
                    value={issuePriority}
                    onChange={(e) => setIssuePriority(e.target.value as MaintenancePriority)}
                    className="rounded border px-2 py-1 text-sm"
                  >
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                    <option value="urgent">Urgent</option>
                  </select>
                  <button
                    type="submit"
                    className="rounded bg-blue-600 px-3 py-1 text-sm text-white"
                  >
                    Report
                  </button>
                </form>
                <ul className="mt-2 space-y-1">
                  {(maintByLease[l.id] ?? []).map((m) => (
                    <li key={m.id} className="rounded border p-2">
                      <span className="font-medium text-gray-800">{m.title}</span>{" "}
                      <span className="text-xs text-gray-500">
                        {m.priority} · {m.status}
                      </span>
                      <p className="text-gray-600">{m.description}</p>
                      {m.image_urls.length > 0 && (
                        <div className="mt-1 flex gap-1">
                          {m.image_urls.map((u) => (
                            // eslint-disable-next-line @next/next/no-img-element
                            <img
                              key={u}
                              src={`${API_BASE_URL}${u}`}
                              alt=""
                              className="h-12 w-12 rounded object-cover"
                            />
                          ))}
                        </div>
                      )}
                      <div className="mt-1 flex items-center gap-3">
                        <label className="cursor-pointer text-xs text-blue-600">
                          Add image
                          <input
                            type="file"
                            accept="image/*"
                            className="hidden"
                            aria-label="Add maintenance image"
                            onChange={async (e) => {
                              const file = e.target.files?.[0];
                              if (file) {
                                await uploadMaintenanceImage(m.id, file);
                                await refreshMaint(l.id);
                              }
                            }}
                          />
                        </label>
                        {(m.status === "open" || m.status === "in_progress") && (
                          <button
                            onClick={async () => {
                              await cancelMaintenance(m.id);
                              await refreshMaint(l.id);
                            }}
                            className="text-xs text-red-600"
                          >
                            Cancel
                          </button>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            </li>
          ))}
          {myLeases.length === 0 && <li className="text-gray-500">No lease yet.</li>}
        </ul>
        <div className="mt-6 flex gap-3">
          <Link href="/app/messages" className="rounded border px-3 py-1 text-blue-600">
            Messages{unread > 0 ? ` (${unread})` : ""}
          </Link>
          <Link href="/app/profile" className="rounded border px-3 py-1 text-blue-600">
            Contact info
          </Link>
          <Link href="/app/change-password" className="rounded border px-3 py-1 text-blue-600">
            Change password
          </Link>
          <button onClick={logOut} className="rounded border px-3 py-1">
            Log out
          </button>
        </div>
      </main>
    );
  }

  return (
    <AppShell me={me} unread={unread} onLogOut={logOut}>
      <PageHeader title="Dashboard" />
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
        <div className="min-w-0 space-y-5">
          {stats && (
            <>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                <StatCard label="Outstanding" value={`$${stats.outstanding}`} />
                <StatCard label="Overdue" value={`$${stats.overdue}`} tone="danger" />
                <StatCard label="Collected this month" value={`$${stats.collected_this_month}`} />
                <StatCard
                  label="Properties"
                  value={`${stats.properties_occupied} of ${stats.properties_total} occupied`}
                />
                <StatCard label="Active leases" value={String(stats.active_leases)} />
                <StatCard label="Tenants" value={String(stats.tenants)} />
              </div>
              <Card title="Monthly income">
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart data={stats.monthly_income}>
                    <XAxis dataKey="month" stroke="var(--ink-muted)" fontSize={12} />
                    <YAxis stroke="var(--ink-muted)" fontSize={12} />
                    <Tooltip
                      contentStyle={{
                        background: "var(--surface)",
                        border: "1px solid var(--line)",
                        borderRadius: 12,
                        color: "var(--ink)",
                      }}
                    />
                    {/* isAnimationActive off: with React StrictMode the entry
                        animation can leave the bars stranded at zero height. */}
                    <Bar
                      dataKey="amount"
                      fill="var(--brand)"
                      radius={[6, 6, 0, 0]}
                      isAnimationActive={false}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </Card>
            </>
          )}
          <Card title="Recent payments">
            {recent.length === 0 ? (
              <EmptyState>No payments yet.</EmptyState>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="text-xs text-muted">
                    <tr>
                      <th className="pb-2 font-medium">Date</th>
                      <th className="pb-2 font-medium">Property</th>
                      <th className="pb-2 font-medium">Tenant</th>
                      <th className="pb-2 font-medium">Method</th>
                      <th className="pb-2 text-right font-medium">Amount</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {recent.map((p) => (
                      <tr key={p.id}>
                        <td className="py-2 text-muted">{p.paid_on}</td>
                        <td className="py-2 text-text">{p.property_address}</td>
                        <td className="py-2 text-muted">{p.tenant_name}</td>
                        <td className="py-2">
                          <Badge tone="brand">{p.method.replace("_", " ")}</Badge>
                        </td>
                        <td className="py-2 text-right font-medium text-text">${p.amount}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
        <Card
          title="My properties"
          actions={
            <Link href="/app/properties" className="text-sm text-brand">
              View all
            </Link>
          }
        >
          {properties.length === 0 ? (
            <EmptyState>No properties yet.</EmptyState>
          ) : (
            <ul className="space-y-2">
              {properties.slice(0, 6).map((p) => (
                <li key={p.id} className="flex items-center gap-3 rounded-lg border border-border p-2">
                  {p.image_urls[0] ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={`${API_BASE_URL}${p.image_urls[0]}`}
                      alt=""
                      className="h-12 w-12 shrink-0 rounded-lg object-cover"
                    />
                  ) : (
                    <span className="h-12 w-12 shrink-0 rounded-lg bg-surface-2" />
                  )}
                  <span className="min-w-0">
                    <Link
                      href={`/app/properties/${p.id}`}
                      className="block truncate font-medium text-text"
                    >
                      {p.address}
                    </Link>
                    <Badge tone={p.status === "occupied" ? "success" : "warning"}>{p.status}</Badge>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </AppShell>
  );
}
