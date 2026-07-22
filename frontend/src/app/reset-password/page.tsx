"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { apiFetch, ApiError } from "@/lib/api";
import { AuthFrame } from "@/components/auth-frame";
import { Button, Input } from "@/components/ui";

function ResetForm() {
  const router = useRouter();
  const token = useSearchParams().get("token") ?? "";
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await apiFetch("/api/v1/auth/reset-password", {
        method: "POST",
        body: JSON.stringify({ token, new_password: password }),
      });
      router.push("/login?reset=success");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Reset failed");
    }
  }

  if (!token) {
    return (
      <p data-testid="missing-token" className="text-sm text-danger">
        This reset link is invalid or missing its token.
      </p>
    );
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <p className="text-sm text-muted">Enter your new password.</p>
      {error && (
        <p className="text-sm text-danger" role="alert">
          {error}
        </p>
      )}
      <Input
        type="password"
        required
        minLength={8}
        placeholder="New password (min 8 chars)"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
      />
      <Button type="submit" className="w-full">
        Update password
      </Button>
    </form>
  );
}

export default function ResetPasswordPage() {
  return (
    <AuthFrame title="Set a new password">
      <Suspense>
        <ResetForm />
      </Suspense>
      <p className="text-sm">
        <Link href="/login" className="text-brand-fg">
          Back to log in
        </Link>
      </p>
    </AuthFrame>
  );
}
