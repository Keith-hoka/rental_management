"use client";

import { useEffect, useState } from "react";
import { ApiError } from "@/lib/api";
import { getMe, updateProfile, type Me } from "@/lib/profile";
import { AppShell } from "@/components/app-shell";
import { PortalShell } from "@/components/portal-shell";
import { useShell } from "@/components/use-shell";
import { Button, Card, Field, Input, PageHeader } from "@/components/ui";

export default function ProfilePage() {
  const { me: user, unread, logOut } = useShell();
  // Its own fetch: useShell only carries the name and role the chrome needs,
  // while this page owns the editable record, phone included.
  const [profile, setProfile] = useState<Me | null>(null);
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    let active = true;
    getMe()
      .then((m) => active && setProfile(m))
      .catch(() => active && setError("Could not load profile"));
    return () => {
      active = false;
    };
  }, [user]);

  if (!user) return null;

  const Shell = user.role === "tenant" ? PortalShell : AppShell;

  function startEdit() {
    if (!profile) return;
    setName(profile.name);
    setPhone(profile.phone ?? "");
    setStatus(null);
    setError(null);
    setEditing(true);
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      setProfile(await updateProfile({ name, phone }));
      setEditing(false);
      setStatus("Saved");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Save failed");
    }
  }

  return (
    <Shell me={user} unread={unread} onLogOut={logOut}>
      <div className="mx-auto max-w-lg">
        <PageHeader title="Profile" />
        {error && (
          <p className="mb-3 text-sm text-danger" role="alert">
            {error}
          </p>
        )}
        {status && <p className="mb-3 text-sm text-success">{status}</p>}

        {profile && (
          <Card>
            {editing ? (
              <form onSubmit={onSubmit} className="space-y-3">
                <Field label="Name">
                  <Input
                    required
                    placeholder="Your name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                  />
                </Field>
                <Field label="Phone">
                  <Input
                    placeholder="Phone (optional)"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                  />
                </Field>
                <Button type="submit" className="w-full">
                  Save
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  className="w-full"
                  onClick={() => setEditing(false)}
                >
                  Cancel
                </Button>
              </form>
            ) : (
              <>
                <dl className="text-sm">
                  {[
                    ["Name", profile.name],
                    ["Email", profile.email],
                    ["Phone", profile.phone || "—"],
                  ].map(([label, value]) => (
                    <div key={label} className="flex justify-between border-b border-border py-2">
                      <dt className="text-muted">{label}</dt>
                      <dd className="font-medium text-text">{value}</dd>
                    </div>
                  ))}
                </dl>
                <Button className="mt-4 w-full" onClick={startEdit}>
                  Edit
                </Button>
              </>
            )}
          </Card>
        )}
      </div>
    </Shell>
  );
}
