"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { getAccessToken } from "@/lib/auth";
import {
  listNotifications,
  markAllRead,
  markRead,
  type NotificationInfo,
} from "@/lib/notifications";

const FILTERS = [
  { label: "All categories", value: "" },
  { label: "Lease", value: "lease" },
  { label: "Rent", value: "rent" },
  { label: "Maintenance", value: "maintenance" },
];

export default function MessagesPage() {
  const router = useRouter();
  const [items, setItems] = useState<NotificationInfo[]>([]);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    let active = true;
    listNotifications()
      .then((n) => {
        if (active) setItems(n);
      })
      .catch(() => {
        if (active) setItems([]);
      });
    return () => {
      active = false;
    };
  }, [router]);

  async function refresh() {
    setItems(await listNotifications());
  }

  const shown = filter ? items.filter((n) => n.category.startsWith(filter)) : items;
  const unread = items.filter((n) => n.read_at === null).length;

  return (
    <main className="mx-auto max-w-2xl p-8">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Messages</h1>
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-600">{unread} unread</span>
          <select
            aria-label="Filter category"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="rounded border px-2 py-1 text-sm"
          >
            {FILTERS.map((f) => (
              <option key={f.value} value={f.value}>
                {f.label}
              </option>
            ))}
          </select>
          <button
            onClick={async () => {
              await markAllRead();
              await refresh();
            }}
            className="rounded border px-3 py-1 text-sm text-blue-600"
          >
            Mark all read
          </button>
        </div>
      </div>
      <ul className="space-y-2">
        {shown.map((n) => (
          <li key={n.id} className="rounded border p-3 text-sm">
            <div className="flex items-center justify-between">
              <span
                className={n.read_at === null ? "font-semibold text-gray-900" : "text-gray-700"}
              >
                {n.read_at === null && (
                  <span className="mr-2 inline-block h-2 w-2 rounded-full bg-blue-600" />
                )}
                {n.title}
              </span>
              <span className="text-xs text-gray-500">
                {new Date(n.created_at).toLocaleDateString()}
              </span>
            </div>
            <p className="text-gray-600">{n.body}</p>
            <div className="mt-1 flex items-center gap-3">
              {n.link && (
                <Link href={n.link} className="text-xs text-blue-600">
                  View
                </Link>
              )}
              {n.read_at === null && (
                <button
                  onClick={async () => {
                    await markRead(n.id);
                    await refresh();
                  }}
                  className="text-xs text-blue-600"
                >
                  Mark read
                </button>
              )}
            </div>
          </li>
        ))}
        {shown.length === 0 && <li className="text-gray-500">No messages yet.</li>}
      </ul>
      <p className="mt-6">
        <Link href="/app" className="text-blue-600">
          Back to dashboard
        </Link>
      </p>
    </main>
  );
}
