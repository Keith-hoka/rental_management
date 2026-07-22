import type { CoTenant } from "@/lib/leases";
import { Button, Input } from "@/components/ui";

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
      <p className="text-sm font-semibold text-text">Main tenant</p>
      <Input
        required
        placeholder="Tenant name"
        value={tenantName}
        onChange={(e) => onMain("tenant_name", e.target.value)}
      />
      <Input
        type="email"
        required
        placeholder="Tenant email"
        value={tenantEmail}
        onChange={(e) => onMain("tenant_email", e.target.value)}
      />
      <Input
        placeholder="Tenant phone (optional)"
        value={tenantPhone}
        onChange={(e) => onMain("tenant_phone", e.target.value)}
      />
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold text-text">Co-tenants</p>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={() => onCoTenants([...coTenants, { name: "", email: "", phone: "" }])}
        >
          Add co-tenant
        </Button>
      </div>
      {coTenants.map((c, i) => (
        <div key={i} className="flex gap-2">
          <Input
            required
            placeholder="Name"
            aria-label={`Co-tenant ${i + 1} name`}
            value={c.name}
            onChange={(e) => updateCo(i, "name", e.target.value)}
          />
          <Input
            type="email"
            required
            placeholder="Email"
            aria-label={`Co-tenant ${i + 1} email`}
            value={c.email}
            onChange={(e) => updateCo(i, "email", e.target.value)}
          />
          <Input
            placeholder="Phone"
            aria-label={`Co-tenant ${i + 1} phone`}
            value={c.phone}
            onChange={(e) => updateCo(i, "phone", e.target.value)}
          />
          <Button
            type="button"
            variant="danger"
            size="sm"
            aria-label={`Remove co-tenant ${i + 1}`}
            onClick={() => onCoTenants(coTenants.filter((_, idx) => idx !== i))}
          >
            Remove
          </Button>
        </div>
      ))}
    </div>
  );
}
