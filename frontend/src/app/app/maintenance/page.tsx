"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { API_BASE_URL } from "@/lib/api";
import { getAccessToken } from "@/lib/auth";
import {
  listMaintenance,
  updateMaintenance,
  type MaintenanceInfo,
  type MaintenancePriority,
  type MaintenanceStatus,
} from "@/lib/maintenance";

const STATUSES: MaintenanceStatus[] = ["open", "in_progress", "resolved", "cancelled"];
const PRIORITIES: MaintenancePriority[] = ["low", "medium", "high", "urgent"];

export default function MaintenancePage() {
  const router = useRouter();
  const [requests, setRequests] = useState<MaintenanceInfo[]>([]);
  const [filter, setFilter] = useState<MaintenanceStatus | "">("");

  useEffect(() => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    let active = true;
    listMaintenance(filter || undefined)
      .then((r) => {
        if (active) setRequests(r);
      })
      .catch(() => {
        if (active) setRequests([]);
      });
    return () => {
      active = false;
    };
  }, [router, filter]);

  async function onChange(
    id: string,
    body: { status?: MaintenanceStatus; priority?: MaintenancePriority },
  ) {
    await updateMaintenance(id, body);
    setRequests(await listMaintenance(filter || undefined));
  }

  return (
    <main className="mx-auto max-w-3xl p-8">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Maintenance</h1>
        <select
          aria-label="Filter status"
          value={filter}
          onChange={(e) => setFilter(e.target.value as MaintenanceStatus | "")}
          className="rounded border px-3 py-2"
        >
          <option value="">All statuses</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>
      <ul className="space-y-3">
        {requests.map((m) => (
          <li key={m.id} className="rounded border p-3 text-sm">
            <div className="flex justify-between">
              <span className="font-medium text-gray-800">
                {m.property_address} · {m.title}
              </span>
              <span className="text-xs text-gray-500">by {m.reported_by}</span>
            </div>
            <p className="text-gray-600">{m.description}</p>
            {m.image_urls.length > 0 && (
              <div className="mt-1 flex gap-1">
                {m.image_urls.map((u) => (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    key={u}
                    src={`${API_BASE_URL}${u}`}
                    alt=""
                    className="h-14 w-14 rounded object-cover"
                  />
                ))}
              </div>
            )}
            <div className="mt-2 flex gap-2">
              <select
                aria-label="Status"
                value={m.status}
                onChange={(e) => onChange(m.id, { status: e.target.value as MaintenanceStatus })}
                className="rounded border px-2 py-1"
              >
                {STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
              <select
                aria-label="Set priority"
                value={m.priority}
                onChange={(e) =>
                  onChange(m.id, { priority: e.target.value as MaintenancePriority })
                }
                className="rounded border px-2 py-1"
              >
                {PRIORITIES.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </div>
          </li>
        ))}
        {requests.length === 0 && <li className="text-gray-500">No maintenance requests yet.</li>}
      </ul>
      <p className="mt-6">
        <Link href="/app" className="text-blue-600">
          Back to dashboard
        </Link>
      </p>
    </main>
  );
}
