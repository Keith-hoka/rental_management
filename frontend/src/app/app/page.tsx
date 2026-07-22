"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { apiFetch, API_BASE_URL } from "@/lib/api";
import { clearTokens, getAccessToken } from "@/lib/auth";
import { listMyLeases, type TenantLease } from "@/lib/tenants";
import { listMyLeaseCharges, type ChargeInfo } from "@/lib/charges";
import { getDashboardStats, type DashboardStats } from "@/lib/stats";
import {
  createMaintenance,
  listLeaseMaintenance,
  cancelMaintenance,
  uploadMaintenanceImage,
  type MaintenanceInfo,
  type MaintenancePriority,
} from "@/lib/maintenance";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

interface Me {
  email: string;
  name: string;
  role: string;
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border p-3">
      <p className="text-xs text-gray-500">{label}</p>
      <p className="text-lg font-semibold text-gray-800">{value}</p>
    </div>
  );
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
    <main className="p-8">
      <h1 className="text-2xl font-semibold">Dashboard</h1>
      <p data-testid="welcome" className="mt-2 text-gray-700">
        Welcome, {me.name} ({me.role})
      </p>
      {stats && (
        <>
          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
            <StatCard label="Outstanding" value={`$${stats.outstanding}`} />
            <StatCard label="Overdue" value={`$${stats.overdue}`} />
            <StatCard label="Collected this month" value={`$${stats.collected_this_month}`} />
            <StatCard
              label="Properties"
              value={`${stats.properties_occupied} of ${stats.properties_total} occupied`}
            />
            <StatCard label="Active leases" value={String(stats.active_leases)} />
            <StatCard label="Tenants" value={String(stats.tenants)} />
          </div>
          <h2 className="mb-2 mt-6 font-semibold">Monthly income</h2>
          <div className="mb-2">
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={stats.monthly_income}>
                <XAxis dataKey="month" />
                <YAxis />
                <Tooltip />
                <Bar dataKey="amount" fill="#2563eb" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </>
      )}
      <div className="mt-4 flex gap-3">
        <Link href="/app/properties" className="rounded border px-3 py-1 text-blue-600">
          Properties
        </Link>
        <Link href="/app/leases" className="rounded border px-3 py-1 text-blue-600">
          Leases
        </Link>
        <Link href="/app/team" className="rounded border px-3 py-1 text-blue-600">
          Team
        </Link>
        <Link href="/app/change-password" className="rounded border px-3 py-1 text-blue-600">
          Change password
        </Link>
        <Link href="/app/profile" className="rounded border px-3 py-1 text-blue-600">
          Contact info
        </Link>
        <button onClick={logOut} className="rounded border px-3 py-1">
          Log out
        </button>
      </div>
    </main>
  );
}
