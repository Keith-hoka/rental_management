"use client";

import { useState } from "react";
import Link from "next/link";
import { apiFetch, ApiError } from "@/lib/api";
import { AuthFrame } from "@/components/auth-frame";
import { Button, Input } from "@/components/ui";

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
    <AuthFrame title="Reset your password">
      {sent ? (
        <p data-testid="confirmation" className="text-sm text-text">
          If an account exists for that email, we have sent a reset link.
        </p>
      ) : (
        <form onSubmit={onSubmit} className="space-y-4">
          <p className="text-sm text-muted">Enter your email and we will send a reset link.</p>
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
          <Button type="submit" className="w-full">
            Send reset link
          </Button>
        </form>
      )}
      <p className="text-sm">
        <Link href="/login" className="text-brand">
          Back to log in
        </Link>
      </p>
    </AuthFrame>
  );
}
