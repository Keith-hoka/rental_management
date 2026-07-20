"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ApiError } from "@/lib/api";
import { getAccessToken } from "@/lib/auth";
import {
  createInvitation,
  listInvitations,
  revokeInvitation,
  type Invitation,
} from "@/lib/invitations";

export default function TeamPage() {
  const router = useRouter();
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    listInvitations()
      .then(setInvitations)
      .catch(() => setInvitations([]));
  }, [router]);

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

  return (
    <main className="mx-auto max-w-lg p-8">
      <h1 className="mb-4 text-2xl font-semibold">Team</h1>
      <p className="mb-4 text-sm text-gray-600">
        Invite a property manager to help manage your organization.
      </p>
      {error && (
        <p className="mb-2 text-sm text-red-600" role="alert">
          {error}
        </p>
      )}
      <form onSubmit={onInvite} className="mb-6 flex gap-2">
        <input
          type="email"
          required
          placeholder="Email to invite"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="flex-1 rounded border px-3 py-2"
        />
        <button type="submit" className="rounded bg-blue-600 px-3 py-2 text-white">
          Invite
        </button>
      </form>
      <h2 className="mb-2 font-semibold">Pending invitations</h2>
      <ul className="space-y-2">
        {invitations.map((inv) => (
          <li key={inv.id} className="flex items-center justify-between rounded border p-3">
            <span>
              {inv.email} <span className="text-sm text-gray-500">({inv.role})</span>
            </span>
            <button
              onClick={() => onRevoke(inv.id)}
              className="rounded border border-red-500 px-2 py-1 text-sm text-red-600 transition hover:bg-red-50"
            >
              Revoke
            </button>
          </li>
        ))}
        {invitations.length === 0 && <li className="text-gray-500">No pending invitations.</li>}
      </ul>
      <p className="mt-6">
        <Link href="/app" className="text-blue-600">
          Back to dashboard
        </Link>
      </p>
    </main>
  );
}
