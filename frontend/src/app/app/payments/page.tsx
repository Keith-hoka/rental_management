"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { clearTokens, getAccessToken } from "@/lib/auth";
import { getUnreadCount } from "@/lib/notifications";
import { listRecentPayments, type RecentPayment } from "@/lib/payments";
import { AppShell } from "@/components/app-shell";
import { Badge, Card, EmptyState, PageHeader } from "@/components/ui";

interface Me {
  email: string;
  name: string;
  role: string;
}

export default function PaymentsPage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [unread, setUnread] = useState(0);
  const [payments, setPayments] = useState<RecentPayment[]>([]);

  useEffect(() => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    let active = true;
    apiFetch<Me>("/api/v1/auth/me")
      .then((m) => {
        if (!active) return;
        setMe(m);
        getUnreadCount()
          .then((u) => active && setUnread(u.count))
          .catch(() => active && setUnread(0));
        listRecentPayments(100)
          .then((p) => active && setPayments(p))
          .catch(() => active && setPayments([]));
      })
      .catch(() => {
        clearTokens();
        router.replace("/login");
      });
    return () => {
      active = false;
    };
  }, [router]);

  if (!me) return null;

  function logOut() {
    clearTokens();
    router.replace("/login");
  }

  const total = payments.reduce((sum, p) => sum + Number(p.amount), 0);

  return (
    <AppShell me={me} unread={unread} onLogOut={logOut}>
      <PageHeader title="Payments" />
      <Card title="Payment history" actions={<span className="text-sm text-muted">${total}</span>}>
        {payments.length === 0 ? (
          <EmptyState>No payments yet.</EmptyState>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-border bg-surface-2 text-xs text-muted">
                <tr>
                  <th className="px-3 py-2 font-medium">Date</th>
                  <th className="px-3 py-2 font-medium">Property info</th>
                  <th className="px-3 py-2 font-medium">Tenant name</th>
                  <th className="px-3 py-2 font-medium">Method</th>
                  <th className="px-3 py-2 text-right font-medium">Amount</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {payments.map((p) => (
                  <tr key={p.id}>
                    <td className="px-3 py-2 text-muted">{p.paid_on}</td>
                    <td className="px-3 py-2 text-text">{p.property_address}</td>
                    <td className="px-3 py-2 text-muted">{p.tenant_name}</td>
                    <td className="px-3 py-2">
                      <Badge tone="brand">{p.method.replace("_", " ")}</Badge>
                    </td>
                    <td className="px-3 py-2 text-right font-medium text-text">${p.amount}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </AppShell>
  );
}
