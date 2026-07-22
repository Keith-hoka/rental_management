"use client";

import { useEffect, useState } from "react";
import { ApiError } from "@/lib/api";
import {
  createContractor,
  deleteContractor,
  listContractors,
  type ContractorInfo,
} from "@/lib/contractors";
import { AppShell } from "@/components/app-shell";
import { useShell } from "@/components/use-shell";
import {
  Button,
  Card,
  ConfirmDialog,
  DataList,
  DataRow,
  EmptyState,
  Field,
  Input,
  PageHeader,
} from "@/components/ui";

export default function ContractorsPage() {
  const { me, unread, logOut } = useShell();
  const [contractors, setContractors] = useState<ContractorInfo[]>([]);
  const [name, setName] = useState("");
  const [trade, setTrade] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  useEffect(() => {
    if (!me) return;
    let active = true;
    listContractors()
      .then((c) => active && setContractors(c))
      .catch(() => active && setContractors([]));
    return () => {
      active = false;
    };
  }, [me]);

  async function onAdd(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await createContractor({
        name,
        trade: trade || null,
        phone: phone || null,
        email: email || null,
      });
      setName("");
      setTrade("");
      setPhone("");
      setEmail("");
      setContractors(await listContractors());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not add the contractor");
    }
  }

  async function onDelete(id: string) {
    setError(null);
    setDeleting(null);
    try {
      await deleteContractor(id);
      setContractors(await listContractors());
    } catch (err) {
      // A contractor still assigned to requests comes back 409 with a count.
      setError(err instanceof ApiError ? err.message : "Could not delete the contractor");
    }
  }

  if (!me) return null;

  return (
    <AppShell me={me} unread={unread} onLogOut={logOut}>
      <PageHeader title="Contractors" />
      {error && (
        <p className="mb-3 text-sm text-danger" role="alert">
          {error}
        </p>
      )}
      <Card className="mb-5">
        <form onSubmit={onAdd} className="flex flex-wrap items-end gap-2">
          <div className="min-w-40 flex-1">
            <Field label="Name">
              <Input required value={name} onChange={(e) => setName(e.target.value)} />
            </Field>
          </div>
          <div className="min-w-32 flex-1">
            <Field label="Trade">
              <Input value={trade} onChange={(e) => setTrade(e.target.value)} />
            </Field>
          </div>
          <div className="min-w-32 flex-1">
            <Field label="Phone">
              <Input value={phone} onChange={(e) => setPhone(e.target.value)} />
            </Field>
          </div>
          <div className="min-w-40 flex-1">
            <Field label="Email">
              <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
            </Field>
          </div>
          <Button type="submit">Add contractor</Button>
        </form>
      </Card>
      <DataList>
        {contractors.map((c) => (
          <DataRow key={c.id}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="min-w-0">
                <span className="font-medium text-text">{c.name}</span>
                {c.trade && <span className="text-muted"> · {c.trade}</span>}
                <span className="block text-muted">
                  {c.phone ?? "no phone"} · {c.email ?? "no email - work orders cannot be sent"}
                </span>
              </span>
              <Button variant="danger" size="sm" onClick={() => setDeleting(c.id)}>
                Delete
              </Button>
            </div>
          </DataRow>
        ))}
        {contractors.length === 0 && (
          <DataRow>
            <EmptyState>No contractors yet.</EmptyState>
          </DataRow>
        )}
      </DataList>
      <ConfirmDialog
        open={deleting !== null}
        label="Delete contractor"
        message="Delete this contractor? This cannot be undone."
        confirmLabel="Yes, delete"
        onConfirm={() => deleting && onDelete(deleting)}
        onCancel={() => setDeleting(null)}
      />
    </AppShell>
  );
}
