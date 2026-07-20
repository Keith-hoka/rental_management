"use client";

import { use, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { getAccessToken } from "@/lib/auth";
import { listLeases, type Lease } from "@/lib/leases";

export default function PropertyLeasesPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const [leases, setLeases] = useState<Lease[]>([]);

  useEffect(() => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    let active = true;
    listLeases(id)
      .then((l) => {
        if (active) setLeases(l);
      })
      .catch(() => {
        if (active) setLeases([]);
      });
    return () => {
      active = false;
    };
  }, [id, router]);

  return (
    <main className="mx-auto max-w-lg p-8">
      <h1 className="mb-4 text-2xl font-semibold">Leases</h1>
      <p className="mb-4 text-sm text-gray-600">
        This property&apos;s leases. Add new leases from the{" "}
        <Link href="/app/leases" className="text-blue-600">
          Leases page
        </Link>
        .
      </p>
      <ul className="space-y-2">
        {leases.map((lease) => (
          <li key={lease.id} className="rounded border p-3">
            <Link href={`/app/leases/${lease.id}`} className="text-blue-600">
              {lease.tenant_name}
            </Link>
            <span className="ml-2 text-sm text-gray-600">
              {lease.start_date} to {lease.end_date}
            </span>
          </li>
        ))}
        {leases.length === 0 && <li className="text-gray-500">No leases yet.</li>}
      </ul>
      <p className="mt-6">
        <Link href={`/app/properties/${id}`} className="text-blue-600">
          Back to property
        </Link>
      </p>
    </main>
  );
}
