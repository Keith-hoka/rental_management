"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { getAccessToken } from "@/lib/auth";
import { listAllLeases, type LeaseState, type LeaseSummary } from "@/lib/leases";

const STATE_STYLES: Record<LeaseState, string> = {
  active: "bg-green-100 text-green-800",
  upcoming: "bg-blue-100 text-blue-800",
  ended: "bg-gray-100 text-gray-600",
};

export default function AllLeasesPage() {
  const router = useRouter();
  const [leases, setLeases] = useState<LeaseSummary[]>([]);

  useEffect(() => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    listAllLeases()
      .then(setLeases)
      .catch(() => setLeases([]));
  }, [router]);

  return (
    <main className="mx-auto max-w-2xl p-8">
      <h1 className="mb-4 text-2xl font-semibold">Leases</h1>
      <ul className="space-y-2">
        {leases.map((lease) => (
          <li key={lease.id} className="flex items-center justify-between rounded border p-3">
            <span className="text-sm">
              <Link
                href={`/app/properties/${lease.property_id}/leases`}
                className="font-medium text-blue-600"
              >
                {lease.property_address}
              </Link>
              <span className="text-gray-600">
                {" "}
                · {lease.tenant_name} · {lease.start_date} to {lease.end_date}
              </span>
            </span>
            <span className={`rounded px-2 py-1 text-xs ${STATE_STYLES[lease.state]}`}>
              {lease.state}
            </span>
          </li>
        ))}
        {leases.length === 0 && <li className="text-gray-500">No leases yet.</li>}
      </ul>
      <p className="mt-6">
        <Link href="/app" className="text-blue-600">
          Back to dashboard
        </Link>
      </p>
    </main>
  );
}
