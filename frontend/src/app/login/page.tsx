"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { apiFetch, ApiError } from "@/lib/api";
import { saveTokens, type TokenPair } from "@/lib/auth";

function LoginForm() {
  const router = useRouter();
  const resetDone = useSearchParams().get("reset") === "success";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const tokens = await apiFetch<TokenPair>("/api/v1/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      saveTokens(tokens);
      router.push("/app");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Login failed");
    }
  }

  return (
    <form onSubmit={onSubmit} className="w-full max-w-sm space-y-4 rounded-lg bg-white p-8 shadow">
      <h1 className="text-2xl font-semibold">Log in</h1>
      {resetDone && (
        <p data-testid="reset-success" className="text-sm text-green-700">
          Password updated. Please log in.
        </p>
      )}
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
      <input
        type="password"
        required
        placeholder="Password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        className="w-full rounded border px-3 py-2"
      />
      <button type="submit" className="w-full rounded bg-blue-600 py-2 text-white">
        Log in
      </button>
      <div className="flex justify-between text-sm text-gray-600">
        <Link href="/signup" className="text-blue-600">
          Sign up
        </Link>
        <Link href="/forgot-password" className="text-blue-600">
          Forgot password?
        </Link>
      </div>
    </form>
  );
}

export default function LoginPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-gray-50">
      <Suspense>
        <LoginForm />
      </Suspense>
    </main>
  );
}
