"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { apiFetch, ApiError } from "@/lib/api";
import { saveTokens, type TokenPair } from "@/lib/auth";
import { AuthFrame } from "@/components/auth-frame";
import { Button, Input } from "@/components/ui";

export default function SignupPage() {
  const router = useRouter();
  const [form, setForm] = useState({
    name: "",
    organization_name: "",
    email: "",
    password: "",
  });
  const [error, setError] = useState<string | null>(null);

  function update(field: keyof typeof form) {
    return (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [field]: e.target.value });
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const tokens = await apiFetch<TokenPair>("/api/v1/auth/signup", {
        method: "POST",
        body: JSON.stringify(form),
      });
      saveTokens(tokens);
      router.push("/app");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Signup failed");
    }
  }

  return (
    <AuthFrame title="Create account">
      <form onSubmit={onSubmit} className="space-y-4">
        {error && (
          <p className="text-sm text-danger" role="alert">
            {error}
          </p>
        )}
        <Input required placeholder="Your name" value={form.name} onChange={update("name")} />
        <Input
          required
          placeholder="Organization name"
          value={form.organization_name}
          onChange={update("organization_name")}
        />
        <Input
          type="email"
          required
          placeholder="Email"
          value={form.email}
          onChange={update("email")}
        />
        <Input
          type="password"
          required
          minLength={8}
          placeholder="Password (min 8 chars)"
          value={form.password}
          onChange={update("password")}
        />
        <Button type="submit" className="w-full">
          Sign up
        </Button>
        <p className="text-sm text-muted">
          Have an account?{" "}
          <Link href="/login" className="text-brand">
            Log in
          </Link>
        </p>
      </form>
    </AuthFrame>
  );
}
