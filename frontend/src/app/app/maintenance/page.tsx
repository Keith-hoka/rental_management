"use client";

import { useEffect, useState } from "react";
import { API_BASE_URL } from "@/lib/api";
import {
  listMaintenance,
  updateMaintenance,
  type MaintenanceInfo,
  type MaintenancePriority,
  type MaintenanceStatus,
} from "@/lib/maintenance";
import { AppShell } from "@/components/app-shell";
import { useShell } from "@/components/use-shell";
import { Badge, DataList, DataRow, EmptyState, PageHeader, Select } from "@/components/ui";

const STATUSES: MaintenanceStatus[] = ["open", "in_progress", "resolved", "cancelled"];
const PRIORITIES: MaintenancePriority[] = ["low", "medium", "high", "urgent"];

const STATUS_TONES: Record<MaintenanceStatus, "brand" | "warning" | "success" | "neutral"> = {
  open: "brand",
  in_progress: "warning",
  resolved: "success",
  cancelled: "neutral",
};

const PRIORITY_TONES: Record<MaintenancePriority, "danger" | "warning" | "neutral"> = {
  urgent: "danger",
  high: "danger",
  medium: "warning",
  low: "neutral",
};

export default function MaintenancePage() {
  const { me, unread, logOut } = useShell();
  const [requests, setRequests] = useState<MaintenanceInfo[]>([]);
  const [filter, setFilter] = useState<MaintenanceStatus | "">("");

  useEffect(() => {
    if (!me) return;
    let active = true;
    listMaintenance(filter || undefined)
      .then((r) => active && setRequests(r))
      .catch(() => active && setRequests([]));
    return () => {
      active = false;
    };
  }, [me, filter]);

  async function onChange(
    id: string,
    body: { status?: MaintenanceStatus; priority?: MaintenancePriority },
  ) {
    await updateMaintenance(id, body);
    setRequests(await listMaintenance(filter || undefined));
  }

  if (!me) return null;

  return (
    <AppShell me={me} unread={unread} onLogOut={logOut}>
      <PageHeader
        title="Maintenance"
        actions={
          <Select
            aria-label="Filter status"
            value={filter}
            onChange={(e) => setFilter(e.target.value as MaintenanceStatus | "")}
            className="w-48"
          >
            <option value="">All statuses</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </Select>
        }
      />
      <DataList>
        {requests.map((m) => (
          <DataRow key={m.id}>
            <div className="flex flex-wrap justify-between gap-2">
              <span className="font-medium text-text">
                {m.property_address} · {m.title}
              </span>
              <span className="flex items-center gap-2">
                <Badge tone={PRIORITY_TONES[m.priority]}>{m.priority}</Badge>
                <Badge tone={STATUS_TONES[m.status]}>{m.status}</Badge>
                <span className="text-xs text-muted">by {m.reported_by}</span>
              </span>
            </div>
            <p className="mt-1 text-muted">{m.description}</p>
            {m.image_urls.length > 0 && (
              <div className="mt-2 flex gap-1">
                {m.image_urls.map((u) => (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    key={u}
                    src={`${API_BASE_URL}${u}`}
                    alt=""
                    className="h-14 w-14 rounded-lg object-cover"
                  />
                ))}
              </div>
            )}
            <div className="mt-2 flex gap-2">
              <Select
                aria-label="Status"
                value={m.status}
                onChange={(e) => onChange(m.id, { status: e.target.value as MaintenanceStatus })}
                className="w-40"
              >
                {STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </Select>
              <Select
                aria-label="Set priority"
                value={m.priority}
                onChange={(e) =>
                  onChange(m.id, { priority: e.target.value as MaintenancePriority })
                }
                className="w-40"
              >
                {PRIORITIES.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </Select>
            </div>
          </DataRow>
        ))}
        {requests.length === 0 && (
          <DataRow>
            <EmptyState>No maintenance requests yet.</EmptyState>
          </DataRow>
        )}
      </DataList>
    </AppShell>
  );
}
