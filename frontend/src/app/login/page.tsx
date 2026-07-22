"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { apiFetch, ApiError } from "@/lib/api";
import { saveTokens, type TokenPair } from "@/lib/auth";
import { AuthFrame } from "@/components/auth-frame";
import { Button, Input } from "@/components/ui";

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
    <form onSubmit={onSubmit} className="space-y-4">
      {resetDone && (
        <p data-testid="reset-success" className="text-sm text-success">
          Password updated. Please log in.
        </p>
      )}
      {error && (
        <p className="text-sm text-danger" role="alert">
          {error}
        </p>
      )}
      <Input
        type="email"
        required
        placeholder="Email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
      />
      <Input
        type="password"
        required
        placeholder="Password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
      />
      <Button type="submit" className="w-full">
        Log in
      </Button>
      <div className="flex justify-between text-sm">
        <Link href="/signup" className="text-brand">
          Sign up
        </Link>
        <Link href="/forgot-password" className="text-brand">
          Forgot password?
        </Link>
      </div>
    </form>
  );
}

export default function LoginPage() {
  return (
    <AuthFrame title="Log in">
      <Suspense>
        <LoginForm />
      </Suspense>
    </AuthFrame>
  );
}
