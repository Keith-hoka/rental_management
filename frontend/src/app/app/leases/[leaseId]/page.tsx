"use client";

import { use, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ApiError } from "@/lib/api";
import { getAccessToken } from "@/lib/auth";
import {
  deleteLease,
  getLease,
  updateLease,
  type Lease,
  type LeaseInput,
} from "@/lib/leases";
import { getProperty, type Property } from "@/lib/properties";
import { listLeaseCharges, type ChargeInfo } from "@/lib/charges";
import {
  recordPayment,
  listLeasePayments,
  deleteLeasePayment,
  getLeaseBalance,
  type PaymentInfo,
  type BalanceInfo,
  type PaymentMethod,
} from "@/lib/payments";
import { TenantFields } from "@/app/app/leases/TenantFields";
import {
  inviteTenant,
  listLeaseInvitations,
  listLeaseReminders,
  listLeaseTenants,
  revokeLeaseInvitation,
  type LeaseInvitationInfo,
  type LeaseReminderInfo,
  type LeaseTenantInfo,
} from "@/lib/tenants";

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between border-b py-2">
      <dt className="text-gray-500">{label}</dt>
      <dd className="font-medium text-gray-800">{value}</dd>
    </div>
  );
}

function ChargeBadge({ status, overdue }: { status: string; overdue: boolean }) {
  const label = overdue ? "Overdue" : status.charAt(0).toUpperCase() + status.slice(1);
  const color = overdue
    ? "bg-red-100 text-red-800"
    : status === "paid"
      ? "bg-green-100 text-green-800"
      : status === "partial"
        ? "bg-yellow-100 text-yellow-800"
        : "bg-gray-100 text-gray-700";
  return <span className={`rounded px-2 py-0.5 text-xs ${color}`}>{label}</span>;
}

export default function LeaseDetailPage({ params }: { params: Promise<{ leaseId: string }> }) {
  const { leaseId } = use(params);
  const router = useRouter();
  const [lease, setLease] = useState<Lease | null>(null);
  const [property, setProperty] = useState<Property | null>(null);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<LeaseInput | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [joined, setJoined] = useState<LeaseTenantInfo[]>([]);
  const [pending, setPending] = useState<LeaseInvitationInfo[]>([]);
  const [reminders, setReminders] = useState<LeaseReminderInfo[]>([]);
  const [charges, setCharges] = useState<ChargeInfo[]>([]);
  const [balance, setBalance] = useState<BalanceInfo | null>(null);
  const [payments, setPayments] = useState<PaymentInfo[]>([]);
  const [payAmount, setPayAmount] = useState("");
  const [payDate, setPayDate] = useState("");
  const [payMethod, setPayMethod] = useState<PaymentMethod>("bank_transfer");
  const [payNote, setPayNote] = useState("");
  const [inviteStatus, setInviteStatus] = useState<string | null>(null);
  const [inviteError, setInviteError] = useState<string | null>(null);

  useEffect(() => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    let active = true;
    getLease(leaseId)
      .then((l) => {
        if (!active) return;
        setLease(l);
        return getProperty(l.property_id).then((p) => {
          if (active) setProperty(p);
        });
      })
      .catch(() => {
        if (active) setError("Lease not found");
      });
    listLeaseTenants(leaseId)
      .then((t) => {
        if (active) setJoined(t);
      })
      .catch(() => {
        if (active) setJoined([]);
      });
    listLeaseInvitations(leaseId)
      .then((p) => {
        if (active) setPending(p);
      })
      .catch(() => {
        if (active) setPending([]);
      });
    listLeaseReminders(leaseId)
      .then((r) => {
        if (active) setReminders(r);
      })
      .catch(() => {
        if (active) setReminders([]);
      });
    listLeaseCharges(leaseId)
      .then((c) => {
        if (active) setCharges(c);
      })
      .catch(() => {
        if (active) setCharges([]);
      });
    getLeaseBalance(leaseId)
      .then((b) => {
        if (active) setBalance(b);
      })
      .catch(() => {
        if (active) setBalance(null);
      });
    listLeasePayments(leaseId)
      .then((p) => {
        if (active) setPayments(p);
      })
      .catch(() => {
        if (active) setPayments([]);
      });
    return () => {
      active = false;
    };
  }, [leaseId, router]);

  if (error && !lease) return <main className="p-8 text-red-600">{error}</main>;
  if (!lease) return null;

  function set<K extends keyof LeaseInput>(key: K, value: LeaseInput[K]) {
    setForm((f) => (f ? { ...f, [key]: value } : f));
  }

  function startEdit(current: Lease) {
    setError(null);
    setForm({
      tenant_name: current.tenant_name,
      tenant_email: current.tenant_email,
      tenant_phone: current.tenant_phone ?? "",
      co_tenants: current.co_tenants.map((c) => ({
        name: c.name,
        email: c.email,
        phone: c.phone ?? "",
      })),
      rent_amount: current.rent_amount,
      rent_frequency: current.rent_frequency,
      bond_amount: current.bond_amount,
      notice_period_days: current.notice_period_days,
      start_date: current.start_date,
      end_date: current.end_date,
    });
    setEditing(true);
  }

  async function onSave(e: React.FormEvent) {
    e.preventDefault();
    if (!form) return;
    setError(null);
    try {
      setLease(await updateLease(leaseId, form));
      setEditing(false);
      setForm(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Save failed");
    }
  }

  async function onDelete() {
    await deleteLease(leaseId);
    router.push("/app/leases");
  }

  async function refreshTenants() {
    const [j, p] = await Promise.all([listLeaseTenants(leaseId), listLeaseInvitations(leaseId)]);
    setJoined(j);
    setPending(p);
  }

  async function onInvite(email: string) {
    setInviteError(null);
    setInviteStatus(null);
    try {
      await inviteTenant(leaseId, email);
      setInviteStatus(`Invitation sent to ${email}`);
      await refreshTenants();
    } catch (err) {
      setInviteError(err instanceof ApiError ? err.message : "Invite failed");
    }
  }

  async function onRevoke(invitationId: string) {
    setInviteError(null);
    setInviteStatus(null);
    try {
      await revokeLeaseInvitation(leaseId, invitationId);
      await refreshTenants();
    } catch (err) {
      setInviteError(err instanceof ApiError ? err.message : "Revoke failed");
    }
  }

  async function refreshMoney() {
    const [c, b, p] = await Promise.all([
      listLeaseCharges(leaseId),
      getLeaseBalance(leaseId),
      listLeasePayments(leaseId),
    ]);
    setCharges(c);
    setBalance(b);
    setPayments(p);
  }

  async function onRecordPayment(e: React.FormEvent) {
    e.preventDefault();
    await recordPayment(leaseId, {
      amount: Number(payAmount),
      paid_on: payDate,
      method: payMethod,
      note: payNote || null,
    });
    setPayAmount("");
    setPayDate("");
    setPayNote("");
    await refreshMoney();
  }

  async function onDeletePayment(paymentId: string) {
    await deleteLeasePayment(leaseId, paymentId);
    await refreshMoney();
  }

  return (
    <main className="mx-auto max-w-lg p-8">
      <h1 className="mb-4 text-2xl font-semibold">{editing ? "Edit lease" : "Lease"}</h1>
      {error && (
        <p className="mb-2 text-sm text-red-600" role="alert">
          {error}
        </p>
      )}

      {editing && form ? (
        <form onSubmit={onSave} className="mb-6 space-y-3">
          <TenantFields
            tenantName={form.tenant_name}
            tenantEmail={form.tenant_email}
            tenantPhone={form.tenant_phone}
            coTenants={form.co_tenants}
            onMain={(field, value) => set(field, value)}
            onCoTenants={(next) => set("co_tenants", next)}
          />
          <div className="flex gap-2">
            <label className="flex-1 text-sm text-gray-600">
              Rent
              <input
                type="number"
                min={0}
                required
                value={form.rent_amount || ""}
                onChange={(e) => set("rent_amount", Number(e.target.value))}
                className="mt-1 w-full rounded border px-3 py-2"
              />
            </label>
            <label className="flex-1 text-sm text-gray-600">
              Frequency
              <select
                value={form.rent_frequency}
                onChange={(e) => set("rent_frequency", e.target.value as LeaseInput["rent_frequency"])}
                className="mt-1 w-full rounded border px-3 py-2"
              >
                <option value="weekly">Weekly</option>
                <option value="fortnightly">Fortnightly</option>
                <option value="monthly">Monthly</option>
              </select>
            </label>
          </div>
          <div className="flex gap-2">
            <label className="flex-1 text-sm text-gray-600">
              Bond (optional)
              <input
                type="number"
                min={0}
                value={form.bond_amount ?? ""}
                onChange={(e) =>
                  set("bond_amount", e.target.value === "" ? null : Number(e.target.value))
                }
                className="mt-1 w-full rounded border px-3 py-2"
              />
            </label>
            <label className="flex-1 text-sm text-gray-600">
              Notice period (days)
              <input
                type="number"
                min={0}
                value={form.notice_period_days ?? ""}
                onChange={(e) =>
                  set("notice_period_days", e.target.value === "" ? null : Number(e.target.value))
                }
                className="mt-1 w-full rounded border px-3 py-2"
              />
            </label>
          </div>
          <div className="flex gap-2">
            <label className="flex-1 text-sm text-gray-600">
              Start
              <input
                type="date"
                required
                value={form.start_date}
                onChange={(e) => set("start_date", e.target.value)}
                className="mt-1 w-full rounded border px-3 py-2"
              />
            </label>
            <label className="flex-1 text-sm text-gray-600">
              End
              <input
                type="date"
                required
                value={form.end_date}
                onChange={(e) => set("end_date", e.target.value)}
                className="mt-1 w-full rounded border px-3 py-2"
              />
            </label>
          </div>
          <div className="flex gap-2">
            <button type="submit" className="flex-1 rounded bg-blue-600 py-2 text-white">
              Save lease
            </button>
            <button
              type="button"
              onClick={() => {
                setEditing(false);
                setForm(null);
              }}
              className="flex-1 rounded border py-2 transition hover:bg-gray-50"
            >
              Cancel
            </button>
          </div>
        </form>
      ) : (
        <>
          <dl className="mb-6 text-sm">
            <Field label="Property" value={property?.address ?? "—"} />
            <Field label="Tenant" value={lease.tenant_name} />
            <Field label="Email" value={lease.tenant_email} />
            <Field label="Phone" value={lease.tenant_phone || "—"} />
            {lease.co_tenants.length > 0 && (
              <div className="border-b py-2">
                <p className="mb-2 text-gray-500">Co-tenants</p>
                <ul className="space-y-2">
                  {lease.co_tenants.map((c, i) => (
                    <li key={i} className="rounded bg-gray-50 p-2">
                      <p className="font-medium text-gray-800">{c.name}</p>
                      <p className="text-gray-600">{c.email}</p>
                      {c.phone && <p className="text-gray-600">{c.phone}</p>}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <Field label="Rent" value={`$${lease.rent_amount} / ${lease.rent_frequency}`} />
            <Field
              label="Bond"
              value={lease.bond_amount != null ? `$${lease.bond_amount}` : "—"}
            />
            <Field
              label="Notice period"
              value={
                lease.notice_period_days != null ? `${lease.notice_period_days} days` : "—"
              }
            />
            <Field label="Start" value={lease.start_date} />
            <Field label="End" value={lease.end_date} />
          </dl>
          <div className="flex gap-2">
            <button
              onClick={() => startEdit(lease)}
              className="flex-1 rounded border px-3 py-2 text-blue-600 transition hover:bg-blue-50"
            >
              Edit
            </button>
            <button
              onClick={() => setConfirming(true)}
              className="flex-1 rounded border border-red-500 px-3 py-2 text-red-600 transition hover:bg-red-50"
            >
              Delete
            </button>
          </div>

          <section className="mt-8">
            <h2 className="mb-2 font-semibold">Tenants</h2>
            {inviteStatus && <p className="mb-2 text-sm text-green-700">{inviteStatus}</p>}
            {inviteError && (
              <p className="mb-2 text-sm text-red-600" role="alert">
                {inviteError}
              </p>
            )}
            <ul className="space-y-2">
              {[
                { name: lease.tenant_name, email: lease.tenant_email },
                ...lease.co_tenants.map((c) => ({ name: c.name, email: c.email })),
              ].map((r) => {
                const isJoined = joined.some((t) => t.email === r.email);
                const invite = pending.find((p) => p.email === r.email);
                return (
                  <li
                    key={r.email}
                    className="flex items-center justify-between rounded border p-2 text-sm"
                  >
                    <span>
                      {r.name} <span className="text-gray-500">({r.email})</span>
                    </span>
                    {isJoined ? (
                      <span className="rounded bg-green-100 px-2 py-1 text-xs text-green-800">
                        Joined
                      </span>
                    ) : invite ? (
                      <span className="flex items-center gap-2">
                        <span className="text-xs text-gray-500">Pending</span>
                        <button
                          onClick={() => onRevoke(invite.id)}
                          className="rounded border border-red-500 px-2 py-1 text-red-600 transition hover:bg-red-50"
                        >
                          Revoke
                        </button>
                      </span>
                    ) : (
                      <button
                        onClick={() => onInvite(r.email)}
                        className="rounded border px-2 py-1 text-blue-600 transition hover:bg-blue-50"
                      >
                        Invite
                      </button>
                    )}
                  </li>
                );
              })}
            </ul>
          </section>

          <section className="mt-8">
            <h2 className="mb-2 font-semibold">Expiry reminders</h2>
            {reminders.length === 0 ? (
              <p className="text-sm text-gray-500">No reminders sent yet.</p>
            ) : (
              <ul className="space-y-1 text-sm text-gray-700">
                {reminders.map((r, i) => (
                  <li key={i}>
                    {r.threshold_days}-day reminder - sent{" "}
                    {new Date(r.sent_at).toLocaleDateString()}
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="mt-8">
            <h2 className="mb-2 font-semibold">Rent charges</h2>
            {balance && (
              <p className="mb-2 text-sm text-gray-600">
                Outstanding{" "}
                <span className="font-medium text-gray-800">${balance.outstanding}</span>
                {" · "}Overdue{" "}
                <span className="font-medium text-red-600">${balance.overdue_amount}</span>
                {balance.credit > 0 && (
                  <>
                    {" · "}Credit{" "}
                    <span className="font-medium text-green-700">${balance.credit}</span>
                  </>
                )}
              </p>
            )}
            {charges.length === 0 ? (
              <p className="text-sm text-gray-500">No charges yet.</p>
            ) : (
              <ul className="space-y-1 text-sm text-gray-700">
                {charges.map((c) => (
                  <li key={c.id} className="flex justify-between">
                    <span>
                      {c.period_start} – {c.period_end} · due {c.due_date}
                    </span>
                    <span className="flex items-center gap-2">
                      <span className="text-gray-500">
                        ${c.amount_paid} / ${c.amount_due}
                      </span>
                      <ChargeBadge status={c.status} overdue={c.overdue} />
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="mt-8">
            <h2 className="mb-2 font-semibold">Payments</h2>
            <form onSubmit={onRecordPayment} className="mb-3 flex flex-wrap gap-2">
              <input
                type="number"
                min="0.01"
                step="0.01"
                required
                placeholder="Amount"
                value={payAmount}
                onChange={(e) => setPayAmount(e.target.value)}
                className="w-28 rounded border px-2 py-1 text-sm"
              />
              <input
                type="date"
                required
                aria-label="Payment date"
                value={payDate}
                onChange={(e) => setPayDate(e.target.value)}
                className="rounded border px-2 py-1 text-sm"
              />
              <select
                aria-label="Payment method"
                value={payMethod}
                onChange={(e) => setPayMethod(e.target.value as PaymentMethod)}
                className="rounded border px-2 py-1 text-sm"
              >
                <option value="bank_transfer">Bank transfer</option>
                <option value="cash">Cash</option>
                <option value="other">Other</option>
              </select>
              <input
                type="text"
                placeholder="Note (optional)"
                value={payNote}
                onChange={(e) => setPayNote(e.target.value)}
                className="flex-1 rounded border px-2 py-1 text-sm"
              />
              <button type="submit" className="rounded bg-blue-600 px-3 py-1 text-sm text-white">
                Record payment
              </button>
            </form>
            {payments.length === 0 ? (
              <p className="text-sm text-gray-500">No payments yet.</p>
            ) : (
              <ul className="space-y-1 text-sm text-gray-700">
                {payments.map((p) => (
                  <li key={p.id} className="flex items-center justify-between">
                    <span>
                      {p.paid_on} · ${p.amount} · {p.method}
                      {p.note ? ` · ${p.note}` : ""}
                    </span>
                    <button
                      onClick={() => onDeletePayment(p.id)}
                      className="rounded border border-red-500 px-2 py-0.5 text-xs text-red-600 transition hover:bg-red-50"
                    >
                      Delete
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}

      <p className="mt-6">
        <Link href="/app/leases" className="text-blue-600">
          Back to all leases
        </Link>
      </p>

      {confirming && (
        <div className="fixed inset-0 z-10 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-sm rounded-lg bg-white p-6 shadow-lg">
            <p className="mb-4 text-gray-800">Delete this lease? This cannot be undone.</p>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setConfirming(false)}
                className="rounded border px-3 py-1 transition hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={onDelete}
                className="rounded bg-red-600 px-3 py-1 text-white transition hover:bg-red-700"
              >
                Yes, delete
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
