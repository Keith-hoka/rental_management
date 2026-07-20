"use client";

import { use, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ApiError } from "@/lib/api";
import { getAccessToken } from "@/lib/auth";
import {
  createLease,
  deleteLease,
  listLeases,
  updateLease,
  type Lease,
  type LeaseInput,
} from "@/lib/leases";

const EMPTY: LeaseInput = {
  tenant_name: "",
  tenant_email: "",
  rent_amount: 0,
  rent_frequency: "monthly",
  bond_amount: null,
  notice_period_days: null,
  start_date: "",
  end_date: "",
};

export default function LeasesPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const [leases, setLeases] = useState<Lease[]>([]);
  const [form, setForm] = useState<LeaseInput>(EMPTY);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    listLeases(id)
      .then(setLeases)
      .catch(() => setLeases([]));
  }, [id, router]);

  function set<K extends keyof LeaseInput>(key: K, value: LeaseInput[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function refresh() {
    setLeases(await listLeases(id));
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      if (editingId) {
        await updateLease(editingId, form);
      } else {
        await createLease(id, form);
      }
      setForm(EMPTY);
      setEditingId(null);
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Save failed");
    }
  }

  function startEdit(lease: Lease) {
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

  async function onDelete(leaseId: string) {
    await deleteLease(leaseId);
    if (editingId === leaseId) {
      setEditingId(null);
      setForm(EMPTY);
    }
    await refresh();
  }

  return (
    <main className="mx-auto max-w-lg p-8">
      <h1 className="mb-4 text-2xl font-semibold">Leases</h1>
      {error && (
        <p className="mb-2 text-sm text-red-600" role="alert">
          {error}
        </p>
      )}
      <form onSubmit={onSubmit} className="mb-6 space-y-3">
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
        <button type="submit" className="w-full rounded bg-blue-600 py-2 text-white">
          {editingId ? "Save lease" : "Add lease"}
        </button>
      </form>
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
