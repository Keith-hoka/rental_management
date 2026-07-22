"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { listTenants, type TenantDirectoryEntry } from "@/lib/tenants";
import { AppShell } from "@/components/app-shell";
import { useShell } from "@/components/use-shell";
import { Badge, DataList, DataRow, EmptyState, Input, PageHeader } from "@/components/ui";

export default function TenantsPage() {
  const { me, unread, logOut } = useShell();
  const [tenants, setTenants] = useState<TenantDirectoryEntry[]>([]);
  const [search, setSearch] = useState("");

  useEffect(() => {
    if (!me) return;
    let active = true;
    listTenants()
      .then((t) => active && setTenants(t))
      .catch(() => active && setTenants([]));
    return () => {
      active = false;
    };
  }, [me]);

  if (!me) return null;

  const needle = search.trim().toLowerCase();
  const shown = needle
    ? tenants.filter((t) =>
        `${t.name} ${t.email} ${t.property_address}`.toLowerCase().includes(needle),
      )
    : tenants;

  return (
    <AppShell me={me} unread={unread} onLogOut={logOut}>
      <PageHeader
        title="Tenants"
        actions={
          <Input
            placeholder="Search tenants"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-64"
          />
        }
      />
      <DataList>
        {shown.map((t, i) => (
          <DataRow key={`${t.lease_id}-${t.email}-${i}`}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span>
                <span className="font-medium text-text">{t.name}</span>
                <span className="ml-2 text-muted">{t.email}</span>
                {t.phone && <span className="ml-2 text-muted">{t.phone}</span>}
              </span>
              <span className="flex items-center gap-2">
                <Badge tone={t.joined ? "success" : "neutral"}>
                  {t.joined ? "Joined" : "Not joined"}
                </Badge>
                <Link href={`/app/leases/${t.lease_id}`} className="text-brand-fg">
                  {t.property_address}
                </Link>
              </span>
            </div>
          </DataRow>
        ))}
        {shown.length === 0 && (
          <DataRow>
            <EmptyState>No tenants yet.</EmptyState>
          </DataRow>
        )}
      </DataList>
    </AppShell>
  );
}
