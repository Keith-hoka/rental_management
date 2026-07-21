import type { CoTenant } from "@/lib/leases";

type MainField = "tenant_name" | "tenant_email" | "tenant_phone";

interface Props {
  tenantName: string;
  tenantEmail: string;
  tenantPhone: string;
  coTenants: CoTenant[];
  onMain: (field: MainField, value: string) => void;
  onCoTenants: (next: CoTenant[]) => void;
}

export function TenantFields({
  tenantName,
  tenantEmail,
  tenantPhone,
  coTenants,
  onMain,
  onCoTenants,
}: Props) {
  function updateCo(index: number, field: keyof CoTenant, value: string) {
    onCoTenants(coTenants.map((c, i) => (i === index ? { ...c, [field]: value } : c)));
  }

  return (
    <div className="space-y-3">
      <p className="text-sm font-semibold text-gray-700">Main tenant</p>
      <input
        required
        placeholder="Tenant name"
        value={tenantName}
        onChange={(e) => onMain("tenant_name", e.target.value)}
        className="w-full rounded border px-3 py-2"
      />
      <input
        type="email"
        required
        placeholder="Tenant email"
        value={tenantEmail}
        onChange={(e) => onMain("tenant_email", e.target.value)}
        className="w-full rounded border px-3 py-2"
      />
      <input
        placeholder="Tenant phone (optional)"
        value={tenantPhone}
        onChange={(e) => onMain("tenant_phone", e.target.value)}
        className="w-full rounded border px-3 py-2"
      />
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold text-gray-700">Co-tenants</p>
        <button
          type="button"
          onClick={() => onCoTenants([...coTenants, { name: "", email: "", phone: "" }])}
          className="rounded border px-2 py-1 text-sm text-blue-600 transition hover:bg-blue-50"
        >
          Add co-tenant
        </button>
      </div>
      {coTenants.map((c, i) => (
        <div key={i} className="flex gap-2">
          <input
            required
            placeholder="Name"
            aria-label={`Co-tenant ${i + 1} name`}
            value={c.name}
            onChange={(e) => updateCo(i, "name", e.target.value)}
            className="flex-1 rounded border px-2 py-2"
          />
          <input
            type="email"
            required
            placeholder="Email"
            aria-label={`Co-tenant ${i + 1} email`}
            value={c.email}
            onChange={(e) => updateCo(i, "email", e.target.value)}
            className="flex-1 rounded border px-2 py-2"
          />
          <input
            placeholder="Phone"
            aria-label={`Co-tenant ${i + 1} phone`}
            value={c.phone}
            onChange={(e) => updateCo(i, "phone", e.target.value)}
            className="flex-1 rounded border px-2 py-2"
          />
          <button
            type="button"
            aria-label={`Remove co-tenant ${i + 1}`}
            onClick={() => onCoTenants(coTenants.filter((_, idx) => idx !== i))}
            className="rounded border border-red-500 px-2 text-sm text-red-600 transition hover:bg-red-50"
          >
            Remove
          </button>
        </div>
      ))}
    </div>
  );
}
