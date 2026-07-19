"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { getAccessToken } from "@/lib/auth";
import { listProperties, type Property } from "@/lib/properties";

export default function PropertiesPage() {
  const router = useRouter();
  const [properties, setProperties] = useState<Property[]>([]);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");

  useEffect(() => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    listProperties({ search, status })
      .then(setProperties)
      .catch(() => setProperties([]));
  }, [router, search, status]);

  return (
    <main className="p-8">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Properties</h1>
        <Link href="/app/properties/new" className="rounded bg-blue-600 px-3 py-2 text-white">
          New property
        </Link>
      </div>
      <div className="mb-4 flex gap-2">
        <input
          placeholder="Search address"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="rounded border px-3 py-2"
        />
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="rounded border px-3 py-2"
        >
          <option value="">All statuses</option>
          <option value="vacant">Vacant</option>
          <option value="occupied">Occupied</option>
        </select>
      </div>
      <ul className="space-y-2">
        {properties.map((p) => (
          <li key={p.id} className="rounded border p-3">
            <Link href={`/app/properties/${p.id}`} className="text-blue-600">
              {p.address}
            </Link>
            <span data-testid="status" className="ml-2 text-sm text-gray-600">
              {p.type} - {p.status}
            </span>
          </li>
        ))}
        {properties.length === 0 && <li className="text-gray-500">No properties yet.</li>}
      </ul>
      <p className="mt-6">
        <Link href="/app" className="text-blue-600">
          Back to dashboard
        </Link>
      </p>
    </main>
  );
}
