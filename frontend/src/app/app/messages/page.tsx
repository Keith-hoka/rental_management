"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  listNotifications,
  markAllRead,
  markRead,
  type NotificationInfo,
} from "@/lib/notifications";
import { AppShell } from "@/components/app-shell";
import { useShell } from "@/components/use-shell";
import { Button, DataList, DataRow, EmptyState, PageHeader, Select } from "@/components/ui";

const FILTERS = [
  { label: "All categories", value: "" },
  { label: "Lease", value: "lease" },
  { label: "Rent", value: "rent" },
  { label: "Maintenance", value: "maintenance" },
];

export default function MessagesPage() {
  const { me, unread, logOut } = useShell();
  const [items, setItems] = useState<NotificationInfo[]>([]);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    if (!me) return;
    let active = true;
    listNotifications()
      .then((n) => active && setItems(n))
      .catch(() => active && setItems([]));
    return () => {
      active = false;
    };
  }, [me]);

  async function refresh() {
    setItems(await listNotifications());
  }

  if (!me) return null;

  const shown = filter ? items.filter((n) => n.category.startsWith(filter)) : items;
  const unreadCount = items.filter((n) => n.read_at === null).length;

  return (
    <AppShell me={me} unread={unread} onLogOut={logOut}>
      <PageHeader
        title="Messages"
        actions={
          <>
            <span className="text-sm text-muted">{unreadCount} unread</span>
            <Select
              aria-label="Filter category"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              className="w-44"
            >
              {FILTERS.map((f) => (
                <option key={f.value} value={f.value}>
                  {f.label}
                </option>
              ))}
            </Select>
            <Button
              variant="secondary"
              onClick={async () => {
                await markAllRead();
                await refresh();
              }}
            >
              Mark all read
            </Button>
          </>
        }
      />
      <DataList>
        {shown.map((n) => (
          <DataRow key={n.id}>
            <div className="flex items-center justify-between gap-2">
              <span className={n.read_at === null ? "font-semibold text-text" : "text-muted"}>
                {n.read_at === null && (
                  <span className="mr-2 inline-block h-2 w-2 rounded-full bg-brand" />
                )}
                {n.title}
              </span>
              <span className="text-xs text-muted">
                {new Date(n.created_at).toLocaleDateString()}
              </span>
            </div>
            <p className="text-muted">{n.body}</p>
            <div className="mt-1 flex items-center gap-3">
              {n.link && (
                <Link href={n.link} className="text-xs text-brand">
                  View
                </Link>
              )}
              {n.read_at === null && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={async () => {
                    await markRead(n.id);
                    await refresh();
                  }}
                >
                  Mark read
                </Button>
              )}
            </div>
          </DataRow>
        ))}
        {shown.length === 0 && (
          <DataRow>
            <EmptyState>No messages yet.</EmptyState>
          </DataRow>
        )}
      </DataList>
    </AppShell>
  );
}
