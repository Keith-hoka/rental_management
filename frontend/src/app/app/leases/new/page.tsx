"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ApiError } from "@/lib/api";
import { getAccessToken } from "@/lib/auth";
import { createLease, type LeaseInput } from "@/lib/leases";
import { listProperties, type Property } from "@/lib/properties";
import { TenantFields } from "@/app/app/leases/TenantFields";

function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

function emptyForm(): LeaseInput {
  return {
    tenant_name: "",
    tenant_email: "",
    tenant_phone: "",
    co_tenants: [],
    rent_amount: 0,
    rent_frequency: "monthly",
    bond_amount: null,
    notice_period_days: null,
    start_date: todayISO(),
    end_date: "",
  };
}

export default function NewLeasePage() {
  const router = useRouter();
  const [properties, setProperties] = useState<Property[]>([]);
  const [propertyId, setPropertyId] = useState("");
  const [form, setForm] = useState<LeaseInput>(emptyForm());
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    let active = true;
    listProperties()
      .then((p) => {
        if (active) setProperties(p);
      })
      .catch(() => {
        if (active) setProperties([]);
      });
    return () => {
      active = false;
    };
  }, [router]);

  function set<K extends keyof LeaseInput>(key: K, value: LeaseInput[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await createLease(propertyId, form);
      router.push("/app/leases");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Create failed");
    }
  }

  return (
    <main className="mx-auto max-w-2xl p-8">
      <h1 className="mb-4 text-2xl font-semibold">New lease</h1>
      <p className="mb-4 text-sm text-gray-600">
        Add a lease for one of your properties. A lease covering today makes the property occupied.
      </p>
      {error && (
        <p className="mb-2 text-sm text-red-600" role="alert">
          {error}
        </p>
      )}
      <form onSubmit={onSubmit} className="space-y-3">
        <select
          required
          aria-label="Property"
          value={propertyId}
          onChange={(e) => setPropertyId(e.target.value)}
          className="w-full rounded border px-3 py-2"
        >
          <option value="">Select a property</option>
          {properties.map((p) => (
            <option key={p.id} value={p.id}>{`${p.address} (${p.status})`}</option>
          ))}
        </select>
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
        <button type="submit" className="w-full rounded bg-blue-600 py-2 text-white">
          Add lease
        </button>
      </form>
      <p className="mt-4">
        <Link href="/app/leases" className="text-blue-600">
          Back to all leases
        </Link>
      </p>
    </main>
  );
}
