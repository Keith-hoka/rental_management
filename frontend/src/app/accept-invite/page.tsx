"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { apiFetch, ApiError } from "@/lib/api";
import { saveTokens, type TokenPair } from "@/lib/auth";

function AcceptForm() {
  const router = useRouter();
  const token = useSearchParams().get("token") ?? "";
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const tokens = await apiFetch<TokenPair>("/api/v1/invitations/accept", {
        method: "POST",
        body: JSON.stringify({ token, name, password }),
      });
      saveTokens(tokens);
      router.push("/app");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Accept failed");
    }
  }

  if (!token) {
    return (
      <p data-testid="missing-token" className="text-sm text-red-600">
        This invitation link is invalid or missing its token.
      </p>
    );
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <p className="text-sm text-gray-600">Set up your account to join the team.</p>
      {error && (
        <p className="text-sm text-red-600" role="alert">
          {error}
        </p>
      )}
      <input
        required
        placeholder="Your name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        className="w-full rounded border px-3 py-2"
      />
      <input
        type="password"
        required
        minLength={8}
        placeholder="Password (min 8 chars)"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        className="w-full rounded border px-3 py-2"
      />
      <button type="submit" className="w-full rounded bg-blue-600 py-2 text-white">
        Accept invitation
      </button>
    </form>
  );
}

export default function AcceptInvitePage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-gray-50">
      <div className="w-full max-w-sm space-y-4 rounded-lg bg-white p-8 shadow">
        <h1 className="text-2xl font-semibold">Accept invitation</h1>
        <Suspense>
          <AcceptForm />
        </Suspense>
        <p className="text-sm text-gray-600">
          <Link href="/login" className="text-blue-600">
            Back to log in
          </Link>
        </p>
      </div>
    </main>
  );
}
