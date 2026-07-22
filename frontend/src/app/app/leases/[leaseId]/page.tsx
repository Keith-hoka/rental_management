"use client";

import { use, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ApiError } from "@/lib/api";
import { AppShell } from "@/components/app-shell";
import { useShell } from "@/components/use-shell";
import { Badge, Button, Card, Input, PageHeader, Select } from "@/components/ui";
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
    <div className="flex justify-between border-b border-border py-2">
      <dt className="text-muted">{label}</dt>
      <dd className="font-medium text-text">{value}</dd>
    </div>
  );
}

function ChargeBadge({ status, overdue }: { status: string; overdue: boolean }) {
  const label = overdue ? "Overdue" : status.charAt(0).toUpperCase() + status.slice(1);
  const tone = overdue
    ? "danger"
    : status === "paid"
      ? "success"
      : status === "partial"
        ? "warning"
        : "neutral";
  return <Badge tone={tone}>{label}</Badge>;
}

export default function LeaseDetailPage({ params }: { params: Promise<{ leaseId: string }> }) {
  const { leaseId } = use(params);
  const router = useRouter();
  const { me, unread, logOut } = useShell();
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
    if (!me) return;
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
  }, [leaseId, me]);

  if (!me) return null;
  if (error && !lease)
    return (
      <AppShell me={me} unread={unread} onLogOut={logOut}>
        <p className="text-danger">{error}</p>
      </AppShell>
    );
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
    <AppShell me={me} unread={unread} onLogOut={logOut}>
      <div className="mx-auto max-w-2xl">
        <PageHeader title={editing ? "Edit lease" : "Lease"} />
      {error && (
        <p className="mb-2 text-sm text-danger" role="alert">
          {error}
        </p>
      )}

      {editing && form ? (
        <Card>
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
            <label className="flex-1 text-sm text-muted">
              Rent
              <Input
                type="number"
                min={0}
                required
                value={form.rent_amount || ""}
                onChange={(e) => set("rent_amount", Number(e.target.value))}
                className="mt-1"
              />
            </label>
            <label className="flex-1 text-sm text-muted">
              Frequency
              <Select
                value={form.rent_frequency}
                onChange={(e) => set("rent_frequency", e.target.value as LeaseInput["rent_frequency"])}
                className="mt-1"
              >
                <option value="weekly">Weekly</option>
                <option value="fortnightly">Fortnightly</option>
                <option value="monthly">Monthly</option>
              </Select>
            </label>
          </div>
          <div className="flex gap-2">
            <label className="flex-1 text-sm text-muted">
              Bond (optional)
              <Input
                type="number"
                min={0}
                value={form.bond_amount ?? ""}
                onChange={(e) =>
                  set("bond_amount", e.target.value === "" ? null : Number(e.target.value))
                }
                className="mt-1"
              />
            </label>
            <label className="flex-1 text-sm text-muted">
              Notice period (days)
              <Input
                type="number"
                min={0}
                value={form.notice_period_days ?? ""}
                onChange={(e) =>
                  set("notice_period_days", e.target.value === "" ? null : Number(e.target.value))
                }
                className="mt-1"
              />
            </label>
          </div>
          <div className="flex gap-2">
            <label className="flex-1 text-sm text-muted">
              Start
              <Input
                type="date"
                required
                value={form.start_date}
                onChange={(e) => set("start_date", e.target.value)}
                className="mt-1"
              />
            </label>
            <label className="flex-1 text-sm text-muted">
              End
              <Input
                type="date"
                required
                value={form.end_date}
                onChange={(e) => set("end_date", e.target.value)}
                className="mt-1"
              />
            </label>
          </div>
          <Button type="submit" className="w-full">
            Save lease
          </Button>
          <Button
            type="button"
            variant="secondary"
            className="w-full"
            onClick={() => {
              setEditing(false);
              setForm(null);
            }}
          >
            Cancel
          </Button>
        </form>
        </Card>
      ) : (
        <>
          <Card>
          <dl className="mb-6 text-sm">
            <Field label="Property" value={property?.address ?? "—"} />
            <Field label="Tenant" value={lease.tenant_name} />
            <Field label="Email" value={lease.tenant_email} />
            <Field label="Phone" value={lease.tenant_phone || "—"} />
            {lease.co_tenants.length > 0 && (
              <div className="border-b border-border py-2">
                <p className="mb-2 text-muted">Co-tenants</p>
                <ul className="space-y-2">
                  {lease.co_tenants.map((c, i) => (
                    <li key={i} className="rounded-lg bg-surface-2 p-2">
                      <p className="font-medium text-text">{c.name}</p>
                      <p className="text-muted">{c.email}</p>
                      {c.phone && <p className="text-muted">{c.phone}</p>}
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
          <Button className="w-full" onClick={() => startEdit(lease)}>
            Edit
          </Button>
          <Button variant="danger" className="mt-2 w-full" onClick={() => setConfirming(true)}>
            Delete
          </Button>
          </Card>

          <Card className="mt-5" title="Tenants">
            {inviteStatus && <p className="mb-2 text-sm text-success">{inviteStatus}</p>}
            {inviteError && (
              <p className="mb-2 text-sm text-danger" role="alert">
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
                    className="flex items-center justify-between rounded-lg border border-border p-2 text-sm"
                  >
                    <span>
                      {r.name} <span className="text-muted">({r.email})</span>
                    </span>
                    {isJoined ? (
                      <Badge tone="success">Joined</Badge>
                    ) : invite ? (
                      <span className="flex items-center gap-2">
                        <span className="text-xs text-muted">Pending</span>
                        <Button variant="danger" size="sm" onClick={() => onRevoke(invite.id)}>
                          Revoke
                        </Button>
                      </span>
                    ) : (
                      <Button variant="secondary" size="sm" onClick={() => onInvite(r.email)}>
                        Invite
                      </Button>
                    )}
                  </li>
                );
              })}
            </ul>
          </Card>

          <Card className="mt-5" title="Expiry reminders">
            {reminders.length === 0 ? (
              <p className="text-sm text-muted">No reminders sent yet.</p>
            ) : (
              <ul className="space-y-1 text-sm text-text">
                {reminders.map((r, i) => (
                  <li key={i}>
                    {r.threshold_days}-day reminder - sent{" "}
                    {new Date(r.sent_at).toLocaleDateString()}
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card className="mt-5" title="Rent charges">
            {balance && (
              <p className="mb-2 text-sm text-muted">
                Outstanding{" "}
                <span className="font-medium text-text">${balance.outstanding}</span>
                {" · "}Overdue{" "}
                <span className="font-medium text-danger">${balance.overdue_amount}</span>
                {balance.credit > 0 && (
                  <>
                    {" · "}Credit{" "}
                    <span className="font-medium text-success">${balance.credit}</span>
                  </>
                )}
              </p>
            )}
            {charges.length === 0 ? (
              <p className="text-sm text-muted">No charges yet.</p>
            ) : (
              <ul className="space-y-1 text-sm text-text">
                {charges.map((c) => (
                  <li key={c.id} className="flex justify-between">
                    <span>
                      {c.period_start} – {c.period_end} · due {c.due_date}
                    </span>
                    <span className="flex items-center gap-2">
                      <span className="text-muted">
                        ${c.amount_paid} / ${c.amount_due}
                      </span>
                      <ChargeBadge status={c.status} overdue={c.overdue} />
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card className="mt-5" title="Payments">
            <form onSubmit={onRecordPayment} className="mb-3 flex flex-wrap gap-2">
              <Input
                type="number"
                min="0.01"
                step="0.01"
                required
                placeholder="Amount"
                value={payAmount}
                onChange={(e) => setPayAmount(e.target.value)}
                className="w-28"
              />
              <Input
                type="date"
                required
                aria-label="Payment date"
                value={payDate}
                onChange={(e) => setPayDate(e.target.value)}
                className="w-40"
              />
              <Select
                aria-label="Payment method"
                value={payMethod}
                onChange={(e) => setPayMethod(e.target.value as PaymentMethod)}
                className="w-40"
              >
                <option value="bank_transfer">Bank transfer</option>
                <option value="cash">Cash</option>
                <option value="other">Other</option>
              </Select>
              <Input
                type="text"
                placeholder="Note (optional)"
                value={payNote}
                onChange={(e) => setPayNote(e.target.value)}
                className="flex-1"
              />
              <Button type="submit">Record payment</Button>
            </form>
            {payments.length === 0 ? (
              <p className="text-sm text-muted">No payments yet.</p>
            ) : (
              <ul className="space-y-1 text-sm text-text">
                {payments.map((p) => (
                  <li key={p.id} className="flex items-center justify-between">
                    <span>
                      {p.paid_on} · ${p.amount} · {p.method}
                      {p.note ? ` · ${p.note}` : ""}
                    </span>
                    <Button
                      variant="danger"
                      size="sm"
                      aria-label={`Delete payment of $${p.amount} on ${p.paid_on}`}
                      onClick={() => onDeletePayment(p.id)}
                    >
                      Delete
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </>
      )}

      <p className="mt-6">
        {/* While editing, back means "leave the form", not "leave the lease". */}
        {editing ? (
          <button
            type="button"
            className="text-brand-fg"
            onClick={() => {
              setEditing(false);
              setForm(null);
            }}
          >
            Back
          </button>
        ) : (
          <Link href="/app/leases" className="text-brand-fg">
            Back
          </Link>
        )}
      </p>

      {confirming && (
        <div className="fixed inset-0 z-10 flex items-center justify-center bg-black/40 p-4">
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Delete lease"
            className="w-full max-w-sm rounded-xl border border-border bg-surface p-6 shadow-lg"
          >
            <p className="mb-4 text-text">Delete this lease? This cannot be undone.</p>
            <div className="flex justify-end gap-2">
              <Button variant="secondary" size="sm" onClick={() => setConfirming(false)}>
                Cancel
              </Button>
              <Button variant="danger" size="sm" onClick={onDelete}>
                Yes, delete
              </Button>
            </div>
          </div>
        </div>
      )}
      </div>
    </AppShell>
  );
}
