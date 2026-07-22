"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { formatAddress, getProperty, imageSrc, type Property } from "@/lib/properties";
import { getLeaseBalance, listLeasePayments, type BalanceInfo } from "@/lib/payments";
import { listMaintenance, type MaintenanceInfo } from "@/lib/maintenance";
import { AppShell } from "@/components/app-shell";
import { useShell } from "@/components/use-shell";
import {
  Badge,
  Card,
  DataList,
  DataRow,
  EmptyState,
  PageHeader,
  StatCard,
  linkButton,
  linkButtonOutline,
} from "@/components/ui";

export default function PropertyDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { me, unread, logOut } = useShell();
  const [prop, setProp] = useState<Property | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [balance, setBalance] = useState<BalanceInfo | null>(null);
  const [collected, setCollected] = useState(0);
  const [requests, setRequests] = useState<MaintenanceInfo[]>([]);

  useEffect(() => {
    if (!me) return;
    let active = true;
    getProperty(id)
      .then(async (p) => {
        if (!active) return;
        setProp(p);
        // Money figures come from the active lease; a vacant property has none.
        if (p.active_lease) {
          const [b, payments] = await Promise.all([
            getLeaseBalance(p.active_lease.id).catch(() => null),
            listLeasePayments(p.active_lease.id).catch(() => []),
          ]);
          if (!active) return;
          setBalance(b);
          setCollected(payments.reduce((sum, x) => sum + Number(x.amount), 0));
        }
        const all = await listMaintenance().catch(() => []);
        if (active) setRequests(all.filter((m) => m.property_address === p.address));
      })
      .catch(() => active && setError("Property not found"));
    return () => {
      active = false;
    };
  }, [id, me]);

  if (!me) return null;

  const open = requests.filter((m) => m.status === "open" || m.status === "in_progress");

  return (
    <AppShell me={me} unread={unread} onLogOut={logOut}>
      <div className="mx-auto max-w-3xl">
        {error && (
          <p className="mb-3 text-sm text-danger" role="alert">
            {error}
          </p>
        )}
        {prop && (
          <>
            <PageHeader
              title={formatAddress(prop)}
              actions={
                <>
                  <Link href={`/app/properties/${id}/leases`} className={linkButton}>
                    Leases
                  </Link>
                  <Link href={`/app/properties/${id}/edit`} className={linkButton}>
                    Edit
                  </Link>
                </>
              }
            />

            {prop.image_urls.length > 0 && (
              // auto-fit: a lone photo fills the row and lines up with the cards
              // below, while several share it.
              <div className="mb-5 grid gap-2 [grid-template-columns:repeat(auto-fit,minmax(240px,1fr))]">
                {prop.image_urls.map((url) => (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    key={url}
                    src={imageSrc(url)}
                    alt="Property"
                    className="h-56 w-full rounded-xl object-cover"
                  />
                ))}
              </div>
            )}

            <Card title="Summary" className="mb-5">
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <StatCard label="Rent collected" value={`$${collected.toFixed(2)}`} />
                <StatCard
                  label="Rent due"
                  value={`$${balance?.outstanding ?? 0}`}
                  tone={Number(balance?.overdue_amount ?? 0) > 0 ? "danger" : "default"}
                />
                <StatCard label="Open requests" value={String(open.length)} />
                {/* Not a status card: the Tenancy badge below already says that.
                    The frequency lives in the label so the value stays short. */}
                <StatCard
                  label={prop.active_lease ? `Rent / ${prop.active_lease.rent_frequency}` : "Rent"}
                  value={prop.active_lease ? `$${prop.active_lease.rent_amount}` : "—"}
                />
              </div>
              <p className="mt-3 text-sm text-muted">
                {prop.type} · {prop.bedrooms} bed · {prop.bathrooms} bath · {prop.parking} parking
              </p>
              {prop.description && <p className="mt-1 text-sm text-muted">{prop.description}</p>}
            </Card>

            <Card title="Tenancy" className="mb-5">
              {prop.active_lease ? (
                <>
                  <p className="mb-2">
                    <Badge tone="success">Occupied</Badge>
                  </p>
                  <p className="text-sm text-text">
                    {prop.active_lease.tenant_name} · ${prop.active_lease.rent_amount}/
                    {prop.active_lease.rent_frequency}
                  </p>
                  <p className="text-sm text-muted">
                    {prop.active_lease.start_date} to {prop.active_lease.end_date}
                  </p>
                  <Link
                    href={`/app/leases/${prop.active_lease.id}`}
                    className={`${linkButtonOutline} mt-3`}
                  >
                    Open lease
                  </Link>
                </>
              ) : (
                <p className="text-sm text-muted">Vacant — no active lease.</p>
              )}
            </Card>

            <Card title="Maintenance requests">
              <DataList>
                {requests.map((m) => (
                  <DataRow key={m.id}>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-medium text-text">{m.title}</span>
                      <span className="flex items-center gap-2">
                        <Badge tone={m.priority === "low" ? "neutral" : "warning"}>
                          {m.priority}
                        </Badge>
                        <Badge tone={m.status === "resolved" ? "success" : "brand"}>
                          {m.status}
                        </Badge>
                      </span>
                    </div>
                    <p className="mt-1 text-muted">{m.description}</p>
                  </DataRow>
                ))}
                {requests.length === 0 && (
                  <DataRow>
                    <EmptyState>No maintenance requests for this property.</EmptyState>
                  </DataRow>
                )}
              </DataList>
            </Card>

            <p className="mt-6">
              <Link href="/app/properties" className="text-brand-fg">
                Back
              </Link>
            </p>
          </>
        )}
      </div>
    </AppShell>
  );
}
