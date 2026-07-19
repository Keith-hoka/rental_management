"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { apiFetch, ApiError } from "@/lib/api";
import { getAccessToken } from "@/lib/auth";

export default function ChangePasswordPage() {
  const router = useRouter();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (!getAccessToken()) router.replace("/login");
  }, [router]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (newPassword !== confirmPassword) {
      setError("New passwords do not match");
      return;
    }
    try {
      await apiFetch("/api/v1/auth/change-password", {
        method: "POST",
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      });
      setDone(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Change failed");
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-gray-50">
      <div className="w-full max-w-sm space-y-4 rounded-lg bg-white p-8 shadow">
        <h1 className="text-2xl font-semibold">Change password</h1>
        {done ? (
          <p data-testid="change-success" className="text-sm text-green-700">
            Your password has been changed.
          </p>
        ) : (
          <form onSubmit={onSubmit} className="space-y-4">
            {error && (
              <p data-testid="change-error" className="text-sm text-red-600" role="alert">
                {error}
              </p>
            )}
            <input
              type="password"
              required
              placeholder="Current password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              className="w-full rounded border px-3 py-2"
            />
            <input
              type="password"
              required
              minLength={8}
              placeholder="New password (min 8 chars)"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              className="w-full rounded border px-3 py-2"
            />
            <input
              type="password"
              required
              minLength={8}
              placeholder="Confirm new password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className="w-full rounded border px-3 py-2"
            />
            <button type="submit" className="w-full rounded bg-blue-600 py-2 text-white">
              Update password
            </button>
          </form>
        )}
        <p className="text-sm text-gray-600">
          <Link href="/app" className="text-blue-600">
            Back to dashboard
          </Link>
        </p>
      </div>
    </main>
  );
}
