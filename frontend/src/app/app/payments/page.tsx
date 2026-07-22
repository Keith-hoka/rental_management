"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { clearTokens, getAccessToken } from "@/lib/auth";
import { getUnreadCount } from "@/lib/notifications";
import { listRecentPayments, type RecentPayment } from "@/lib/payments";
import { AppShell } from "@/components/app-shell";
import { PaymentTable } from "@/components/payment-table";
import { Card, PageHeader } from "@/components/ui";

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
      {/* toFixed: the API sends amounts as fixed-point strings, so a summed
          total must be formatted back or it renders as $1800.5 beside $1800.50. */}
      <Card
        title="Payment history"
        actions={<span className="text-sm text-muted">${total.toFixed(2)}</span>}
      >
        <PaymentTable payments={payments} />
      </Card>
    </AppShell>
  );
}
