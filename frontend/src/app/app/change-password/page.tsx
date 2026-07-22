"use client";

import { useState } from "react";
import { apiFetch, ApiError } from "@/lib/api";
import { AppShell } from "@/components/app-shell";
import { PortalShell } from "@/components/portal-shell";
import { useShell } from "@/components/use-shell";
import { Button, Card, Input, PageHeader } from "@/components/ui";

export default function ChangePasswordPage() {
  const { me, unread, logOut } = useShell();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

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

  if (!me) return null;

  const Shell = me.role === "tenant" ? PortalShell : AppShell;

  return (
    <Shell me={me} unread={unread} onLogOut={logOut}>
      <div className="mx-auto max-w-lg">
        <PageHeader title="Change password" />
        <Card>
          {done ? (
            <p data-testid="change-success" className="text-sm text-success">
              Your password has been changed.
            </p>
          ) : (
            <form onSubmit={onSubmit} className="space-y-3">
              {error && (
                <p data-testid="change-error" className="text-sm text-danger" role="alert">
                  {error}
                </p>
              )}
              <Input
                type="password"
                required
                placeholder="Current password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
              />
              <Input
                type="password"
                required
                minLength={8}
                placeholder="New password (min 8 chars)"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
              />
              <Input
                type="password"
                required
                minLength={8}
                placeholder="Confirm new password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
              />
              <Button type="submit" className="w-full">
                Update password
              </Button>
            </form>
          )}
        </Card>
      </div>
    </Shell>
  );
}
