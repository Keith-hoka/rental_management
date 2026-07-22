"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { apiFetch, ApiError } from "@/lib/api";
import { clearTokens, saveTokens, type TokenPair } from "@/lib/auth";
import { AuthFrame } from "@/components/auth-frame";
import { Button, Input } from "@/components/ui";

const ROLES = [
  { value: "landlord", label: "Landlord" },
  { value: "property_manager", label: "Property manager" },
  { value: "tenant", label: "Tenant" },
] as const;

type Role = (typeof ROLES)[number]["value"];

function LoginForm() {
  const router = useRouter();
  const resetDone = useSearchParams().get("reset") === "success";
  const [role, setRole] = useState<Role>("landlord");
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
      // The role belongs to the account, not the login form, so the choice is
      // checked against the real one rather than sent to the server. The message
      // stays generic: naming the real role would disclose it to whoever asked.
      const me = await apiFetch<{ role: string }>("/api/v1/auth/me");
      if (me.role !== role) {
        clearTokens();
        setError("You chose the wrong role. Select the role this account was created with.");
        return;
      }
      router.push("/app");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Login failed");
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <div>
        <p className="mb-2 text-sm text-muted">Select who you are and get started</p>
        {/* Full width to line up with the inputs and the submit button, but the
            segments stay content-sized and spread: equal thirds are too narrow
            for "Property manager", which then wraps onto two lines. */}
        <div
          role="radiogroup"
          aria-label="Role"
          className="flex justify-between gap-1 rounded-lg border border-border bg-surface-2 p-1"
        >
          {ROLES.map((option) => (
            <button
              key={option.value}
              type="button"
              role="radio"
              aria-checked={role === option.value}
              onClick={() => setRole(option.value)}
              className={`rounded-md px-2 py-1.5 text-xs font-medium whitespace-nowrap transition-colors ${
                role === option.value
                  ? "bg-brand text-white"
                  : "text-muted hover:bg-surface hover:text-text"
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>
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
        <Link href="/signup" className="text-brand-fg">
          Sign up
        </Link>
        <Link href="/forgot-password" className="text-brand-fg">
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
