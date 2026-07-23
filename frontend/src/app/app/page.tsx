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
import {
  Bar,
  BarChart,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { AppShell } from "@/components/app-shell";
import { PortalShell } from "@/components/portal-shell";
import { PaymentTable } from "@/components/payment-table";
import { PaymentExportButton } from "@/components/payment-export-button";
import {
  Badge,
  Button,
  Card,
  DataList,
  DataRow,
  EmptyState,
  Input,
  PageHeader,
  Select,
  StatCard,
  Textarea,
  linkButtonOutline,
} from "@/components/ui";
import { listProperties, type Property } from "@/lib/properties";
import { listRecentPayments, type RecentPayment } from "@/lib/payments";

interface Me {
  email: string;
  name: string;
  role: string;
}

// Tokens, never hex: Recharts' own hardcoded #ccc was already caught glowing on
// a dark card, and any literal colour here would repeat that.
const TOOLTIP_STYLE = {
  background: "var(--surface)",
  border: "1px solid var(--line)",
  borderRadius: 12,
  color: "var(--ink)",
};

const STATUS_FILL: Record<string, string> = {
  open: "var(--brand)",
  in_progress: "var(--warning)",
  resolved: "var(--success)",
  cancelled: "var(--line-strong)",
};

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
      <PortalShell me={me} unread={unread} onLogOut={logOut}>
        <PageHeader title={`Welcome, ${me.name}`} />
        {myLeases.length === 0 && <EmptyState>No lease yet.</EmptyState>}
        {myLeases.map((l) => (
          <div key={l.id} className="mb-5 space-y-5">
            <Card title={l.property_address}>
              <p className="mb-2">
                <Badge tone={l.state === "active" ? "success" : "brand"}>{l.state}</Badge>
              </p>
              <p className="text-sm text-text">
                ${l.rent_amount} / {l.rent_frequency}
              </p>
              <p className="text-sm text-muted">
                {l.start_date} to {l.end_date}
                {l.bond_amount != null && ` · Bond $${l.bond_amount}`}
                {l.notice_period_days != null && ` · Notice ${l.notice_period_days} days`}
              </p>
              <p className="mt-1 text-sm text-muted">
                Landlord contact: {l.landlord_name} — {l.landlord_email}
                {l.landlord_phone ? ` — ${l.landlord_phone}` : ""}
              </p>
              <div className="mt-3 grid grid-cols-2 gap-3">
                <StatCard label="Outstanding" value={`$${l.outstanding}`} />
                <StatCard label="Overdue" value={`$${l.overdue_amount}`} tone="danger" />
              </div>
            </Card>

            <Card title="Rent charges">
              <DataList>
                {(chargesByLease[l.id] ?? []).map((c) => (
                  <DataRow key={c.id}>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="text-muted">
                        {c.period_start} – {c.period_end} · due {c.due_date}
                      </span>
                      <span className="flex items-center gap-2">
                        <span className="text-text">
                          ${c.amount_paid} / ${c.amount_due}
                        </span>
                        <Badge tone={c.overdue ? "danger" : c.status === "paid" ? "success" : "neutral"}>
                          {c.overdue ? "Overdue" : c.status}
                        </Badge>
                      </span>
                    </div>
                  </DataRow>
                ))}
                {(chargesByLease[l.id]?.length ?? 0) === 0 && (
                  <DataRow>
                    <EmptyState>No rent charges yet.</EmptyState>
                  </DataRow>
                )}
              </DataList>
            </Card>

            <Card title="Maintenance">
              <form onSubmit={(e) => reportIssue(l.id, e)} className="space-y-3">
                <Input
                  required
                  placeholder="Issue title"
                  value={issueTitle}
                  onChange={(e) => setIssueTitle(e.target.value)}
                />
                <Textarea
                  required
                  placeholder="Description"
                  value={issueDesc}
                  onChange={(e) => setIssueDesc(e.target.value)}
                />
                <Select
                  aria-label="Priority"
                  value={issuePriority}
                  onChange={(e) => setIssuePriority(e.target.value as MaintenancePriority)}
                >
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                  <option value="urgent">Urgent</option>
                </Select>
                <Button type="submit" className="w-full">
                  Report
                </Button>
              </form>

              <div className="mt-4">
                <DataList>
                  {(maintByLease[l.id] ?? []).map((m) => (
                    <DataRow key={m.id}>
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="font-medium text-text">{m.title}</span>
                        <span className="flex items-center gap-2">
                          <Badge tone={m.priority === "low" ? "neutral" : "warning"}>
                            {m.priority}
                          </Badge>
                          <Badge tone={m.status === "resolved" ? "success" : "brand"}>
                            {m.status}
                          </Badge>
                        </span>
                      </div>
                      <p className="mt-1 text-muted">{m.description}</p>
                      {m.contractor_name && (
                        <p className="mt-1 text-sm text-text">
                          Contractor: {m.contractor_name}
                          {m.contractor_phone ? ` (${m.contractor_phone})` : ""}
                        </p>
                      )}
                      {m.image_urls.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-2">
                          {m.image_urls.map((u) => (
                            // eslint-disable-next-line @next/next/no-img-element
                            <img
                              key={u}
                              src={`${API_BASE_URL}${u}`}
                              alt=""
                              className="h-16 w-16 rounded-lg object-cover"
                            />
                          ))}
                        </div>
                      )}
                      <div className="mt-2 flex items-center gap-2">
                        <label className={`${linkButtonOutline} cursor-pointer`}>
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
                          <Button
                            variant="danger"
                            onClick={async () => {
                              await cancelMaintenance(m.id);
                              await refreshMaint(l.id);
                            }}
                          >
                            Cancel
                          </Button>
                        )}
                      </div>
                    </DataRow>
                  ))}
                  {(maintByLease[l.id] ?? []).length === 0 && (
                    <DataRow>
                      <EmptyState>No maintenance requests yet.</EmptyState>
                    </DataRow>
                  )}
                </DataList>
              </div>
            </Card>
          </div>
        ))}
      </PortalShell>
    );
  }

  return (
    <AppShell me={me} unread={unread} onLogOut={logOut}>
      <PageHeader title={`Welcome, ${me.name}`} actions={<PaymentExportButton />} />
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
                <StatCard label="Maintenance requests" value={String(stats.maintenance_open)} />
              </div>
              <Card title="Monthly income">
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart data={stats.monthly_income}>
                    <XAxis dataKey="month" stroke="var(--ink-muted)" fontSize={12} />
                    <YAxis stroke="var(--ink-muted)" fontSize={12} />
                    <Tooltip
                      // Recharts hardcodes the hover highlight to #ccc, which
                      // is a bright slab on a dark card.
                      cursor={{ fill: "var(--surface-2)" }}
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
              <Card title="Occupancy" className="mt-5">
                <ResponsiveContainer width="100%" height={240}>
                  <LineChart data={stats.occupancy}>
                    <XAxis dataKey="month" stroke="var(--ink-muted)" fontSize={12} />
                    {/* Fixed 0-100: left to auto-scale, a drift from 95% to 92%
                        is stretched into a cliff, which is the chart lying. */}
                    <YAxis domain={[0, 100]} unit="%" stroke="var(--ink-muted)" fontSize={12} />
                    <Tooltip
                      cursor={{ stroke: "var(--surface-2)" }}
                      contentStyle={TOOLTIP_STYLE}
                      formatter={(value, _name, entry) =>
                        `${value}% (${entry.payload.occupied} of ${entry.payload.total})`
                      }
                    />
                    <Line
                      type="monotone"
                      dataKey="rate"
                      stroke="var(--brand)"
                      strokeWidth={2}
                      isAnimationActive={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </Card>
              <Card title="Maintenance status" className="mt-5">
                {stats.maintenance_by_status.every((s) => s.count === 0) ? (
                  <EmptyState>No maintenance requests yet.</EmptyState>
                ) : (
                  <ResponsiveContainer width="100%" height={240}>
                    <PieChart>
                      <Tooltip contentStyle={TOOLTIP_STYLE} />
                      <Pie
                        data={stats.maintenance_by_status}
                        dataKey="count"
                        nameKey="status"
                        innerRadius={55}
                        outerRadius={90}
                        isAnimationActive={false}
                      >
                        {stats.maintenance_by_status.map((s) => (
                          <Cell key={s.status} fill={STATUS_FILL[s.status]} />
                        ))}
                      </Pie>
                    </PieChart>
                  </ResponsiveContainer>
                )}
              </Card>
            </>
          )}
        </div>
        <Card
          // min-w-0: as a grid item it otherwise cannot shrink below the
          // min-content of the longest address, which widens the whole grid past
          // the page padding and leaves the cards below it visibly narrower.
          className="min-w-0"
          title="My properties"
          actions={
            <Link href="/app/properties" className="text-sm text-brand-fg">
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
      {/* Full width under both columns, matching the reference layout. */}
      <Card title="Recent payments" className="mt-5">
        <PaymentTable payments={recent} />
      </Card>
    </AppShell>
  );
}
