"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { listAllLeases, type LeaseState, type LeaseSummary } from "@/lib/leases";
import { AppShell } from "@/components/app-shell";
import { useShell } from "@/components/use-shell";
import { Badge, DataList, DataRow, EmptyState, PageHeader, linkButton } from "@/components/ui";

const STATE_TONES: Record<LeaseState, "success" | "brand" | "neutral"> = {
  active: "success",
  upcoming: "brand",
  ended: "neutral",
};

export default function AllLeasesPage() {
  const { me, unread, logOut } = useShell();
  const [leases, setLeases] = useState<LeaseSummary[]>([]);

  useEffect(() => {
    if (!me) return;
    let active = true;
    listAllLeases()
      .then((l) => active && setLeases(l))
      .catch(() => active && setLeases([]));
    return () => {
      active = false;
    };
  }, [me]);

  if (!me) return null;

  return (
    <AppShell me={me} unread={unread} onLogOut={logOut}>
      <PageHeader
        title="Leases"
        actions={
          <Link href="/app/leases/new" className={linkButton}>
            New lease
          </Link>
        }
      />
      <DataList>
        {leases.map((lease) => (
          <DataRow key={lease.id}>
            <div className="flex flex-wrap items-center gap-2">
              <Link href={`/app/leases/${lease.id}`} className="font-medium text-text">
                {lease.property_address}
              </Link>
              <span className="text-muted">
                {lease.tenant_name} · {lease.start_date} to {lease.end_date}
              </span>
              <Badge tone={STATE_TONES[lease.state]}>{lease.state}</Badge>
            </div>
          </DataRow>
        ))}
        {leases.length === 0 && (
          <DataRow>
            <EmptyState>No leases yet.</EmptyState>
          </DataRow>
        )}
      </DataList>
    </AppShell>
  );
}
