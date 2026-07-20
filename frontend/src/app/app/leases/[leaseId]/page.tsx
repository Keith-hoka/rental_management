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

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between border-b py-2">
      <dt className="text-gray-500">{label}</dt>
      <dd className="font-medium text-gray-800">{value}</dd>
    </div>
  );
}

export default function LeaseDetailPage({ params }: { params: Promise<{ leaseId: string }> }) {
  const { leaseId } = use(params);
  const router = useRouter();
  const [lease, setLease] = useState<Lease | null>(null);
  const [property, setProperty] = useState<Property | null>(null);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<LeaseInput | null>(null);
  const [error, setError] = useState<string | null>(null);

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

  return (
    <main className="mx-auto max-w-lg p-8">
      <h1 className="mb-4 text-2xl font-semibold">Lease</h1>
      {error && (
        <p className="mb-2 text-sm text-red-600" role="alert">
          {error}
        </p>
      )}

      {editing && form ? (
        <form onSubmit={onSave} className="mb-6 space-y-3">
          <input
            required
            placeholder="Tenant name"
            value={form.tenant_name}
            onChange={(e) => set("tenant_name", e.target.value)}
            className="w-full rounded border px-3 py-2"
          />
          <input
            type="email"
            required
            placeholder="Tenant email"
            value={form.tenant_email}
            onChange={(e) => set("tenant_email", e.target.value)}
            className="w-full rounded border px-3 py-2"
          />
          <div className="flex gap-2">
            <label className="flex-1 text-sm text-gray-600">
              Rent
              <input
                type="number"
                min={0}
                value={form.rent_amount}
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
              onClick={onDelete}
              className="flex-1 rounded border border-red-500 px-3 py-2 text-red-600 transition hover:bg-red-50"
            >
              Delete
            </button>
          </div>
        </>
      )}

      <p className="mt-6">
        <Link href="/app/leases" className="text-blue-600">
          Back to all leases
        </Link>
      </p>
    </main>
  );
}
