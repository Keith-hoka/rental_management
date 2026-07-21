"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { apiFetch } from "@/lib/api";
import { clearTokens, getAccessToken } from "@/lib/auth";
import { listMyLeases, type TenantLease } from "@/lib/tenants";
import { listMyLeaseCharges, type ChargeInfo } from "@/lib/charges";

interface Me {
  email: string;
  name: string;
  role: string;
}

export default function DashboardPage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [myLeases, setMyLeases] = useState<TenantLease[]>([]);
  const [chargesByLease, setChargesByLease] = useState<Record<string, ChargeInfo[]>>({});

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
        if (m.role === "tenant") {
          return listMyLeases().then(async (l) => {
            if (!active) return;
            setMyLeases(l);
            const entries = await Promise.all(
              l.map((lease) =>
                listMyLeaseCharges(lease.id)
                  .then((c) => [lease.id, c] as const)
                  .catch(() => [lease.id, []] as const),
              ),
            );
            if (active) setChargesByLease(Object.fromEntries(entries));
          });
        }
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

  if (me.role === "tenant") {
    return (
      <main className="mx-auto max-w-lg p-8">
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <p data-testid="welcome" className="mt-2 text-gray-700">
          Welcome, {me.name} ({me.role})
        </p>
        <h2 className="mb-2 mt-6 font-semibold">Your lease</h2>
        <ul className="space-y-3">
          {myLeases.map((l) => (
            <li key={l.id} className="rounded border p-3 text-sm">
              <p className="font-medium text-gray-800">{l.property_address}</p>
              <p className="text-gray-700">
                ${l.rent_amount} / {l.rent_frequency} · {l.start_date} to {l.end_date} · {l.state}
              </p>
              {l.bond_amount != null && <p className="text-gray-600">Bond: ${l.bond_amount}</p>}
              {l.notice_period_days != null && (
                <p className="text-gray-600">Notice period: {l.notice_period_days} days</p>
              )}
              <p className="mt-1 text-gray-700">
                Landlord contact: {l.landlord_name} — {l.landlord_email}
                {l.landlord_phone ? ` — ${l.landlord_phone}` : ""}
              </p>
              <p className="mt-1 text-gray-700">
                Outstanding <span className="font-medium text-gray-800">${l.outstanding}</span>
                {" · "}Overdue{" "}
                <span className="font-medium text-red-600">${l.overdue_amount}</span>
              </p>
              {(chargesByLease[l.id]?.length ?? 0) > 0 && (
                <ul className="mt-2 space-y-1 text-gray-700">
                  {chargesByLease[l.id].map((c) => (
                    <li key={c.id} className="flex justify-between">
                      <span>
                        {c.period_start} – {c.period_end} · due {c.due_date}
                      </span>
                      <span>
                        ${c.amount_paid} / ${c.amount_due} · {c.overdue ? "Overdue" : c.status}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          ))}
          {myLeases.length === 0 && <li className="text-gray-500">No lease yet.</li>}
        </ul>
        <div className="mt-6 flex gap-3">
          <Link href="/app/profile" className="rounded border px-3 py-1 text-blue-600">
            Contact info
          </Link>
          <Link href="/app/change-password" className="rounded border px-3 py-1 text-blue-600">
            Change password
          </Link>
          <button onClick={logOut} className="rounded border px-3 py-1">
            Log out
          </button>
        </div>
      </main>
    );
  }

  return (
    <main className="p-8">
      <h1 className="text-2xl font-semibold">Dashboard</h1>
      <p data-testid="welcome" className="mt-2 text-gray-700">
        Welcome, {me.name} ({me.role})
      </p>
      <div className="mt-4 flex gap-3">
        <Link href="/app/properties" className="rounded border px-3 py-1 text-blue-600">
          Properties
        </Link>
        <Link href="/app/leases" className="rounded border px-3 py-1 text-blue-600">
          Leases
        </Link>
        <Link href="/app/team" className="rounded border px-3 py-1 text-blue-600">
          Team
        </Link>
        <Link href="/app/change-password" className="rounded border px-3 py-1 text-blue-600">
          Change password
        </Link>
        <Link href="/app/profile" className="rounded border px-3 py-1 text-blue-600">
          Contact info
        </Link>
        <button onClick={logOut} className="rounded border px-3 py-1">
          Log out
        </button>
      </div>
    </main>
  );
}
