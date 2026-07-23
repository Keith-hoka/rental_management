"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { clearTokens, getAccessToken } from "@/lib/auth";
import { getUnreadCount } from "@/lib/notifications";
import { exportPayments, listRecentPayments, type RecentPayment } from "@/lib/payments";
import { getRentSummary, type RentSummary } from "@/lib/rent";
import { downloadBlob } from "@/lib/download";
import { AppShell } from "@/components/app-shell";
import { PaymentTable } from "@/components/payment-table";
import { RentGroups } from "@/components/rent-groups";
import { Button, Card, Input, PageHeader } from "@/components/ui";

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
  const [exportFrom, setExportFrom] = useState("");
  const [exportTo, setExportTo] = useState("");
  const [rent, setRent] = useState<RentSummary>({ overdue: [], upcoming: [] });

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
        getRentSummary()
          .then((r) => active && setRent(r))
          .catch(() => active && setRent({ overdue: [], upcoming: [] }));
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

  async function onExport() {
    const blob = await exportPayments(exportFrom || undefined, exportTo || undefined);
    downloadBlob(blob, "payments.csv");
  }

  const total = payments.reduce((sum, p) => sum + Number(p.amount), 0);

  return (
    <AppShell me={me} unread={unread} onLogOut={logOut}>
      <PageHeader title="Payments" />
      {/* toFixed: the API sends amounts as fixed-point strings, so a summed
          total must be formatted back or it renders as $1800.5 beside $1800.50. */}
      <Card title="Overdue rent" className="mb-5">
        <RentGroups groups={rent.overdue} empty="Nothing overdue." showDaysLate />
      </Card>
      {/* Seven days, not "nothing upcoming": charge_lead_days is 7, so charges
          do not exist beyond it and a longer horizon would be a lie. */}
      <Card title="Upcoming rent" className="mb-5">
        <RentGroups
          groups={rent.upcoming}
          empty="Nothing due in the next 7 days."
          showDaysLate={false}
        />
      </Card>
      <Card
        title="Payment history"
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm text-muted">${total.toFixed(2)}</span>
            <Input
              type="date"
              aria-label="Export from"
              value={exportFrom}
              onChange={(e) => setExportFrom(e.target.value)}
              className="w-40"
            />
            <Input
              type="date"
              aria-label="Export to"
              value={exportTo}
              onChange={(e) => setExportTo(e.target.value)}
              className="w-40"
            />
            <Button variant="secondary" size="sm" onClick={onExport}>
              Export CSV
            </Button>
          </div>
        }
      >
        <PaymentTable payments={payments} />
      </Card>
    </AppShell>
  );
}
