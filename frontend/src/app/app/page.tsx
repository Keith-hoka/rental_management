"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { apiFetch } from "@/lib/api";
import { clearTokens, getAccessToken } from "@/lib/auth";

interface Me {
  email: string;
  name: string;
  role: string;
}

export default function DashboardPage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);

  useEffect(() => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    apiFetch<Me>("/api/v1/auth/me")
      .then(setMe)
      .catch(() => {
        clearTokens();
        router.replace("/login");
      });
  }, [router]);

  if (!me) return null;

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
        <button
          onClick={() => {
            clearTokens();
            router.replace("/login");
          }}
          className="rounded border px-3 py-1"
        >
          Log out
        </button>
      </div>
    </main>
  );
}
