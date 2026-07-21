"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ApiError } from "@/lib/api";
import { getAccessToken } from "@/lib/auth";
import { getMe, updateProfile, type Me } from "@/lib/profile";

export default function ProfilePage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    let active = true;
    getMe()
      .then((m) => {
        if (active) setMe(m);
      })
      .catch(() => {
        if (active) setError("Could not load profile");
      });
    return () => {
      active = false;
    };
  }, [router]);

  if (error && !me) return <main className="p-8 text-red-600">{error}</main>;
  if (!me) return null;

  function startEdit() {
    if (!me) return;
    setName(me.name);
    setPhone(me.phone ?? "");
    setStatus(null);
    setError(null);
    setEditing(true);
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const updated = await updateProfile({ name, phone });
      setMe(updated);
      setEditing(false);
      setStatus("Saved");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Save failed");
    }
  }

  return (
    <main className="mx-auto max-w-lg p-8">
      <h1 className="mb-4 text-2xl font-semibold">Contact info</h1>
      {error && (
        <p className="mb-2 text-sm text-red-600" role="alert">
          {error}
        </p>
      )}
      {status && <p className="mb-2 text-sm text-green-700">{status}</p>}

      {editing ? (
        <form onSubmit={onSubmit} className="space-y-3">
          <input
            required
            placeholder="Your name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full rounded border px-3 py-2"
          />
          <input
            placeholder="Phone (optional)"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            className="w-full rounded border px-3 py-2"
          />
          <div className="flex gap-2">
            <button type="submit" className="flex-1 rounded bg-blue-600 py-2 text-white">
              Save
            </button>
            <button
              type="button"
              onClick={() => setEditing(false)}
              className="flex-1 rounded border py-2 transition hover:bg-gray-50"
            >
              Cancel
            </button>
          </div>
        </form>
      ) : (
        <>
          <dl className="mb-6 text-sm">
            <div className="flex justify-between border-b py-2">
              <dt className="text-gray-500">Name</dt>
              <dd className="font-medium text-gray-800">{me.name}</dd>
            </div>
            <div className="flex justify-between border-b py-2">
              <dt className="text-gray-500">Email</dt>
              <dd className="font-medium text-gray-800">{me.email}</dd>
            </div>
            <div className="flex justify-between border-b py-2">
              <dt className="text-gray-500">Phone</dt>
              <dd className="font-medium text-gray-800">{me.phone || "—"}</dd>
            </div>
          </dl>
          <button
            onClick={startEdit}
            className="rounded border px-3 py-2 text-blue-600 transition hover:bg-blue-50"
          >
            Edit
          </button>
        </>
      )}

      <p className="mt-6">
        <Link href="/app" className="text-blue-600">
          Back to dashboard
        </Link>
      </p>
    </main>
  );
}
