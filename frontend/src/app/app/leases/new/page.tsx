"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ApiError } from "@/lib/api";
import { createLease, type LeaseInput } from "@/lib/leases";
import { listProperties, type Property } from "@/lib/properties";
import { TenantFields } from "@/app/app/leases/TenantFields";
import { AppShell } from "@/components/app-shell";
import { useShell } from "@/components/use-shell";
import { Button, Card, Field, Input, PageHeader, Select } from "@/components/ui";

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
  const { me, unread, logOut } = useShell();
  const [properties, setProperties] = useState<Property[]>([]);
  const [propertyId, setPropertyId] = useState("");
  const [form, setForm] = useState<LeaseInput>(emptyForm());
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!me) return;
    let active = true;
    listProperties()
      .then((p) => active && setProperties(p))
      .catch(() => active && setProperties([]));
    return () => {
      active = false;
    };
  }, [me]);

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

  if (!me) return null;

  return (
    <AppShell me={me} unread={unread} onLogOut={logOut}>
      <div className="mx-auto max-w-2xl">
        <PageHeader title="New lease" />
        <p className="mb-4 text-sm text-muted">
          Add a lease for one of your properties. A lease covering today makes the property
          occupied.
        </p>
        {error && (
          <p className="mb-3 text-sm text-danger" role="alert">
            {error}
          </p>
        )}
      </div>
      <Card className="mx-auto max-w-2xl">
        <form onSubmit={onSubmit} className="space-y-3">
          <Select
            required
            aria-label="Property"
            value={propertyId}
            onChange={(e) => setPropertyId(e.target.value)}
          >
            <option value="">Select a property</option>
            {properties.map((p) => (
              <option key={p.id} value={p.id}>{`${p.address} (${p.status})`}</option>
            ))}
          </Select>
          <TenantFields
            tenantName={form.tenant_name}
            tenantEmail={form.tenant_email}
            tenantPhone={form.tenant_phone}
            coTenants={form.co_tenants}
            onMain={(field, value) => set(field, value)}
            onCoTenants={(next) => set("co_tenants", next)}
          />
          <div className="flex gap-2">
            <div className="flex-1">
              <Field label="Rent">
                <Input
                  type="number"
                  min={0}
                  required
                  value={form.rent_amount || ""}
                  onChange={(e) => set("rent_amount", Number(e.target.value))}
                />
              </Field>
            </div>
            <div className="flex-1">
              <Field label="Frequency">
                <Select
                  value={form.rent_frequency}
                  onChange={(e) =>
                    set("rent_frequency", e.target.value as LeaseInput["rent_frequency"])
                  }
                >
                  <option value="weekly">Weekly</option>
                  <option value="fortnightly">Fortnightly</option>
                  <option value="monthly">Monthly</option>
                </Select>
              </Field>
            </div>
          </div>
          <div className="flex gap-2">
            <div className="flex-1">
              <Field label="Bond (optional)">
                <Input
                  type="number"
                  min={0}
                  value={form.bond_amount ?? ""}
                  onChange={(e) =>
                    set("bond_amount", e.target.value === "" ? null : Number(e.target.value))
                  }
                />
              </Field>
            </div>
            <div className="flex-1">
              <Field label="Notice period (days)">
                <Input
                  type="number"
                  min={0}
                  value={form.notice_period_days ?? ""}
                  onChange={(e) =>
                    set("notice_period_days", e.target.value === "" ? null : Number(e.target.value))
                  }
                />
              </Field>
            </div>
          </div>
          <div className="flex gap-2">
            <div className="flex-1">
              <Field label="Start">
                <Input
                  type="date"
                  required
                  value={form.start_date}
                  onChange={(e) => set("start_date", e.target.value)}
                />
              </Field>
            </div>
            <div className="flex-1">
              <Field label="End">
                <Input
                  type="date"
                  required
                  value={form.end_date}
                  onChange={(e) => set("end_date", e.target.value)}
                />
              </Field>
            </div>
          </div>
          <Button type="submit" className="w-full">
            Add lease
          </Button>
          <Button
            type="button"
            variant="secondary"
            className="w-full"
            onClick={() => router.push("/app/leases")}
          >
            Cancel
          </Button>
        </form>
      </Card>
      <p className="mx-auto mt-4 max-w-2xl">
        <Link href="/app/leases" className="text-brand-fg">
          Back
        </Link>
      </p>
    </AppShell>
  );
}
