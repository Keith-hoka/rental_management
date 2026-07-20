"use client";

import { use, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ApiError } from "@/lib/api";
import { getAccessToken } from "@/lib/auth";
import {
  deleteLease,
  listLeases,
  updateLease,
  type Lease,
  type LeaseInput,
} from "@/lib/leases";

export default function LeasesPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const [leases, setLeases] = useState<Lease[]>([]);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<LeaseInput | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    let active = true;
    listLeases(id)
      .then((l) => {
        if (active) setLeases(l);
      })
      .catch(() => {
        if (active) setLeases([]);
      });
    return () => {
      active = false;
    };
  }, [id, router]);

  function set<K extends keyof LeaseInput>(key: K, value: LeaseInput[K]) {
    setForm((f) => (f ? { ...f, [key]: value } : f));
  }

  function startEdit(lease: Lease) {
    setError(null);
    setEditingId(lease.id);
    setForm({
      tenant_name: lease.tenant_name,
      tenant_email: lease.tenant_email,
      rent_amount: lease.rent_amount,
      rent_frequency: lease.rent_frequency,
      bond_amount: lease.bond_amount,
      notice_period_days: lease.notice_period_days,
      start_date: lease.start_date,
      end_date: lease.end_date,
    });
  }

  function cancelEdit() {
    setEditingId(null);
    setForm(null);
    setError(null);
  }

  async function onSave(e: React.FormEvent) {
    e.preventDefault();
    if (!editingId || !form) return;
    setError(null);
    try {
      await updateLease(editingId, form);
      cancelEdit();
      setLeases(await listLeases(id));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Save failed");
    }
  }

  async function onDelete(leaseId: string) {
    await deleteLease(leaseId);
    if (editingId === leaseId) cancelEdit();
    setLeases(await listLeases(id));
  }

  return (
    <main className="mx-auto max-w-lg p-8">
      <h1 className="mb-4 text-2xl font-semibold">Leases</h1>
      <p className="mb-4 text-sm text-gray-600">
        Edit or remove this property&apos;s leases. Add new leases from the{" "}
        <Link href="/app/leases" className="text-blue-600">
          Leases page
        </Link>
        .
      </p>
      {error && (
        <p className="mb-2 text-sm text-red-600" role="alert">
          {error}
        </p>
      )}
      {editingId && form && (
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
              onClick={cancelEdit}
              className="flex-1 rounded border py-2 transition hover:bg-gray-50"
            >
              Cancel
            </button>
          </div>
        </form>
      )}
      <ul className="space-y-2">
        {leases.map((lease) => (
          <li key={lease.id} className="flex items-center justify-between rounded border p-3">
            <span className="text-sm">
              {lease.tenant_name} · {lease.start_date} to {lease.end_date}
            </span>
            <span className="flex gap-2">
              <button
                onClick={() => startEdit(lease)}
                className="rounded border px-2 py-1 text-sm text-blue-600 transition hover:bg-blue-50"
              >
                Edit
              </button>
              <button
                onClick={() => onDelete(lease.id)}
                className="rounded border border-red-500 px-2 py-1 text-sm text-red-600 transition hover:bg-red-50"
              >
                Delete
              </button>
            </span>
          </li>
        ))}
        {leases.length === 0 && <li className="text-gray-500">No leases yet.</li>}
      </ul>
      <p className="mt-6">
        <Link href={`/app/properties/${id}`} className="text-blue-600">
          Back to property
        </Link>
      </p>
    </main>
  );
}
