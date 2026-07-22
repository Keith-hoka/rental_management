"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { listProperties, type Property } from "@/lib/properties";
import { AppShell } from "@/components/app-shell";
import { useShell } from "@/components/use-shell";
import {
  Badge,
  DataList,
  DataRow,
  EmptyState,
  Input,
  PageHeader,
  Select,
  linkButton,
} from "@/components/ui";

export default function PropertiesPage() {
  const { me, unread, logOut } = useShell();
  const [properties, setProperties] = useState<Property[]>([]);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");

  useEffect(() => {
    if (!me) return;
    let active = true;
    listProperties({ search, status })
      .then((p) => active && setProperties(p))
      .catch(() => active && setProperties([]));
    return () => {
      active = false;
    };
  }, [me, search, status]);

  if (!me) return null;

  return (
    <AppShell me={me} unread={unread} onLogOut={logOut}>
      <PageHeader
        title="Properties"
        actions={
          <Link href="/app/properties/new" className={linkButton}>
            New property
          </Link>
        }
      />
      <div className="mb-4 flex flex-wrap gap-2">
        <Input
          placeholder="Search address"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-xs"
        />
        <Select value={status} onChange={(e) => setStatus(e.target.value)} className="max-w-48">
          <option value="">All statuses</option>
          <option value="vacant">Vacant</option>
          <option value="occupied">Occupied</option>
        </Select>
      </div>
      <DataList>
        {properties.map((p) => (
          <DataRow key={p.id}>
            <div className="flex flex-wrap items-center gap-2">
              <Link href={`/app/properties/${p.id}`} className="font-medium text-text">
                {p.address}
              </Link>
              <span data-testid="status" className="text-muted">
                {p.type} · {p.bedrooms} bed · {p.bathrooms} bath · {p.parking} parking
              </span>
              <Badge tone={p.status === "occupied" ? "success" : "warning"}>{p.status}</Badge>
            </div>
          </DataRow>
        ))}
        {properties.length === 0 && (
          <DataRow>
            <EmptyState>No properties yet.</EmptyState>
          </DataRow>
        )}
      </DataList>
    </AppShell>
  );
}
