"use client";

import { useEffect, useState } from "react";
import { ApiError } from "@/lib/api";
import {
  createInvitation,
  listInvitations,
  revokeInvitation,
  type Invitation,
} from "@/lib/invitations";
import { AppShell } from "@/components/app-shell";
import { useShell } from "@/components/use-shell";
import {
  Badge,
  Button,
  Card,
  DataList,
  DataRow,
  EmptyState,
  Input,
  PageHeader,
} from "@/components/ui";

export default function TeamPage() {
  const { me, unread, logOut } = useShell();
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!me) return;
    let active = true;
    listInvitations()
      .then((i) => active && setInvitations(i))
      .catch(() => active && setInvitations([]));
    return () => {
      active = false;
    };
  }, [me]);

  async function onInvite(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await createInvitation(email);
      setEmail("");
      setInvitations(await listInvitations());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Invite failed");
    }
  }

  async function onRevoke(id: string) {
    await revokeInvitation(id);
    setInvitations(await listInvitations());
  }

  if (!me) return null;

  return (
    <AppShell me={me} unread={unread} onLogOut={logOut}>
      <div className="mx-auto max-w-2xl">
        <PageHeader title="Team" />
        <Card title="Invite a property manager">
          <p className="mb-3 text-sm text-muted">
            Invite a property manager to help manage your organization.
          </p>
          {error && (
            <p className="mb-2 text-sm text-danger" role="alert">
              {error}
            </p>
          )}
          <form onSubmit={onInvite} className="flex gap-2">
            <Input
              type="email"
              required
              placeholder="Email to invite"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            <Button type="submit">Invite</Button>
          </form>
        </Card>

        <Card title="Pending invitations" className="mt-5">
          <DataList>
            {invitations.map((inv) => (
              <DataRow key={inv.id}>
                <div className="flex items-center justify-between gap-2">
                  <span>
                    {inv.email} <Badge tone="neutral">{inv.role}</Badge>
                  </span>
                  <Button variant="danger" size="sm" onClick={() => onRevoke(inv.id)}>
                    Revoke
                  </Button>
                </div>
              </DataRow>
            ))}
            {invitations.length === 0 && (
              <DataRow>
                <EmptyState>No pending invitations.</EmptyState>
              </DataRow>
            )}
          </DataList>
        </Card>
      </div>
    </AppShell>
  );
}
