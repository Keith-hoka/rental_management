"use client";

import { useState } from "react";
import Link from "next/link";
import { apiFetch, ApiError } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await apiFetch("/api/v1/auth/forgot-password", {
        method: "POST",
        body: JSON.stringify({ email }),
      });
      setSent(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Request failed");
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-gray-50">
      <div className="w-full max-w-sm space-y-4 rounded-lg bg-white p-8 shadow">
        <h1 className="text-2xl font-semibold">Reset your password</h1>
        {sent ? (
          <p data-testid="confirmation" className="text-sm text-gray-700">
            If an account exists for that email, we have sent a reset link.
          </p>
        ) : (
          <form onSubmit={onSubmit} className="space-y-4">
            <p className="text-sm text-gray-600">
              Enter your email and we will send a reset link.
            </p>
            {error && (
              <p className="text-sm text-red-600" role="alert">
                {error}
              </p>
            )}
            <input
              type="email"
              required
              placeholder="Email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded border px-3 py-2"
            />
            <button type="submit" className="w-full rounded bg-blue-600 py-2 text-white">
              Send reset link
            </button>
          </form>
        )}
        <p className="text-sm text-gray-600">
          <Link href="/login" className="text-blue-600">
            Back to log in
          </Link>
        </p>
      </div>
    </main>
  );
}
