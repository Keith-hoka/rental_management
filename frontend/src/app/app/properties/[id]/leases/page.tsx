"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { listLeases, type Lease } from "@/lib/leases";
import { AppShell } from "@/components/app-shell";
import { useShell } from "@/components/use-shell";
import { DataList, DataRow, EmptyState, PageHeader } from "@/components/ui";

export default function PropertyLeasesPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { me, unread, logOut } = useShell();
  const [leases, setLeases] = useState<Lease[]>([]);

  useEffect(() => {
    if (!me) return;
    let active = true;
    listLeases(id)
      .then((l) => active && setLeases(l))
      .catch(() => active && setLeases([]));
    return () => {
      active = false;
    };
  }, [id, me]);

  if (!me) return null;

  return (
    <AppShell me={me} unread={unread} onLogOut={logOut}>
      <PageHeader title="Leases" />
      <p className="mb-4 text-sm text-muted">
        This property&apos;s leases. Add new leases from the{" "}
        <Link href="/app/leases" className="text-brand">
          Leases page
        </Link>
        .
      </p>
      <DataList>
        {leases.map((lease) => (
          <DataRow key={lease.id}>
            <Link href={`/app/leases/${lease.id}`} className="font-medium text-text">
              {lease.tenant_name}
            </Link>
            <span className="ml-2 text-muted">
              {lease.start_date} to {lease.end_date}
            </span>
          </DataRow>
        ))}
        {leases.length === 0 && (
          <DataRow>
            <EmptyState>No leases yet.</EmptyState>
          </DataRow>
        )}
      </DataList>
      <p className="mt-6">
        <Link href="/app/properties" className="text-brand">
          Back
        </Link>
      </p>
    </AppShell>
  );
}
