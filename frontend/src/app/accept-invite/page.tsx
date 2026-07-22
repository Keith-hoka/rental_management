"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { apiFetch, ApiError } from "@/lib/api";
import { saveTokens, type TokenPair } from "@/lib/auth";
import { AuthFrame } from "@/components/auth-frame";
import { Button, Input } from "@/components/ui";

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
      <p data-testid="missing-token" className="text-sm text-danger">
        This invitation link is invalid or missing its token.
      </p>
    );
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <p className="text-sm text-muted">Set up your account to join the team.</p>
      {error && (
        <p className="text-sm text-danger" role="alert">
          {error}
        </p>
      )}
      <Input
        required
        placeholder="Your name"
        value={name}
        onChange={(e) => setName(e.target.value)}
      />
      <Input
        type="password"
        required
        minLength={8}
        placeholder="Password (min 8 chars)"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
      />
      <Button type="submit" className="w-full">
        Accept invitation
      </Button>
    </form>
  );
}

export default function AcceptInvitePage() {
  return (
    <AuthFrame title="Accept invitation">
      <Suspense>
        <AcceptForm />
      </Suspense>
      <p className="text-sm">
        <Link href="/login" className="text-brand">
          Back to log in
        </Link>
      </p>
    </AuthFrame>
  );
}
