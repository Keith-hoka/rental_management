"use client";

import { useEffect, useState } from "react";
import {
  createInspection,
  deleteInspection,
  listInspections,
  updateInspection,
  uploadInspectionImage,
  type InspectionCondition,
  type InspectionInfo,
  type InspectionItemIn,
  type InspectionType,
} from "@/lib/inspections";
import { listProperties, type Property } from "@/lib/properties";
import { listAllLeases, type LeaseSummary } from "@/lib/leases";
import { API_BASE_URL } from "@/lib/api";
import { AppShell } from "@/components/app-shell";
import { useShell } from "@/components/use-shell";
import { Badge, Button, Card, ConfirmDialog, Input, PageHeader, Select } from "@/components/ui";

const TYPES: InspectionType[] = ["move_in", "move_out", "routine"];
const CONDITIONS: InspectionCondition[] = ["good", "fair", "poor"];

const TYPE_LABEL: Record<InspectionType, string> = {
  move_in: "Move in",
  move_out: "Move out",
  routine: "Routine",
};

const CONDITION_TONE: Record<InspectionCondition, "success" | "warning" | "danger"> = {
  good: "success",
  fair: "warning",
  poor: "danger",
};

function blankItem(): InspectionItemIn {
  return { area: "", condition: "good", note: "" };
}

/** Repeatable area/condition/note rows shared by the create and edit forms. */
function ItemEditor({
  items,
  onChange,
}: {
  items: InspectionItemIn[];
  onChange: (items: InspectionItemIn[]) => void;
}) {
  const update = (i: number, patch: Partial<InspectionItemIn>) =>
    onChange(items.map((it, idx) => (idx === i ? { ...it, ...patch } : it)));

  return (
    <div className="space-y-2">
      {items.map((it, i) => (
        <div key={i} className="flex flex-wrap items-center gap-2">
          <Input
            type="text"
            placeholder="Area (e.g. Kitchen)"
            aria-label="Item area"
            value={it.area}
            onChange={(e) => update(i, { area: e.target.value })}
            className="w-44"
          />
          <Select
            aria-label="Item condition"
            value={it.condition}
            onChange={(e) => update(i, { condition: e.target.value as InspectionCondition })}
            className="w-32"
          >
            {CONDITIONS.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </Select>
          <Input
            type="text"
            placeholder="Note (optional)"
            aria-label="Item note"
            value={it.note ?? ""}
            onChange={(e) => update(i, { note: e.target.value })}
            className="flex-1"
          />
          <Button
            type="button"
            variant="ghost"
            size="sm"
            aria-label="Remove item"
            onClick={() => onChange(items.filter((_, idx) => idx !== i))}
          >
            Remove
          </Button>
        </div>
      ))}
      <Button type="button" variant="secondary" size="sm" onClick={() => onChange([...items, blankItem()])}>
        Add item
      </Button>
    </div>
  );
}

export default function InspectionsPage() {
  const { me, unread, logOut } = useShell();
  const [inspections, setInspections] = useState<InspectionInfo[]>([]);
  const [properties, setProperties] = useState<Property[]>([]);
  const [leases, setLeases] = useState<LeaseSummary[]>([]);

  const [propertyId, setPropertyId] = useState("");
  const [leaseId, setLeaseId] = useState("");
  const [type, setType] = useState<InspectionType>("move_in");
  const [scheduledFor, setScheduledFor] = useState(() => new Date().toISOString().slice(0, 10));
  const [note, setNote] = useState("");
  const [items, setItems] = useState<InspectionItemIn[]>([]);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState<{
    status: InspectionInfo["status"];
    scheduled_for: string;
    note: string;
    items: InspectionItemIn[];
  } | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  useEffect(() => {
    if (!me) return;
    let active = true;
    listInspections()
      .then((x) => active && setInspections(x))
      .catch(() => active && setInspections([]));
    listProperties()
      .then((p) => active && setProperties(p))
      .catch(() => active && setProperties([]));
    listAllLeases()
      .then((l) => active && setLeases(l))
      .catch(() => active && setLeases([]));
    return () => {
      active = false;
    };
  }, [me]);

  if (!me) return null;

  const addressOf = (id: string) => properties.find((p) => p.id === id)?.address ?? "";
  const leaseChoices = leases.filter((l) => !propertyId || l.property_id === propertyId);

  async function refresh() {
    setInspections(await listInspections());
  }

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    await createInspection({
      property_id: propertyId,
      lease_id: leaseId || null,
      type,
      scheduled_for: scheduledFor,
      note: note || null,
      items: items.filter((it) => it.area.trim()),
    });
    setLeaseId("");
    setNote("");
    setItems([]);
    await refresh();
  }

  function startEdit(x: InspectionInfo) {
    setEditingId(x.id);
    setEditDraft({
      status: x.status,
      scheduled_for: x.scheduled_for,
      note: x.note ?? "",
      items: x.items.map((it) => ({ area: it.area, condition: it.condition, note: it.note ?? "" })),
    });
  }

  async function saveEdit(id: string) {
    if (!editDraft) return;
    await updateInspection(id, {
      status: editDraft.status,
      scheduled_for: editDraft.scheduled_for,
      note: editDraft.note || null,
      items: editDraft.items.filter((it) => it.area.trim()),
    });
    setEditingId(null);
    setEditDraft(null);
    await refresh();
  }

  async function onUpload(id: string, file: File | undefined) {
    if (!file) return;
    await uploadInspectionImage(id, file);
    await refresh();
  }

  async function onDelete(id: string) {
    setDeletingId(null);
    await deleteInspection(id);
    await refresh();
  }

  return (
    <AppShell me={me} unread={unread} onLogOut={logOut}>
      <PageHeader title="Inspections" />

      <Card title="Schedule an inspection">
        <form onSubmit={onCreate} className="space-y-3">
          <div className="flex flex-wrap items-end gap-2">
            <Select
              aria-label="Property"
              required
              value={propertyId}
              onChange={(e) => {
                setPropertyId(e.target.value);
                setLeaseId("");
              }}
              className="w-56"
            >
              <option value="">Select property</option>
              {properties.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.address}
                </option>
              ))}
            </Select>
            <Select
              aria-label="Lease"
              value={leaseId}
              onChange={(e) => setLeaseId(e.target.value)}
              className="w-56"
            >
              <option value="">No lease</option>
              {leaseChoices.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.tenant_name} · {l.property_address}
                </option>
              ))}
            </Select>
            <Select
              aria-label="Type"
              value={type}
              onChange={(e) => setType(e.target.value as InspectionType)}
              className="w-40"
            >
              {TYPES.map((t) => (
                <option key={t} value={t}>
                  {TYPE_LABEL[t]}
                </option>
              ))}
            </Select>
            <Input
              type="date"
              required
              aria-label="Date"
              value={scheduledFor}
              onChange={(e) => setScheduledFor(e.target.value)}
              className="w-40"
            />
            <Input
              type="text"
              placeholder="Note (optional)"
              aria-label="Note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              className="flex-1"
            />
          </div>
          <div>
            <p className="mb-1 text-sm font-medium text-text">Checklist</p>
            <ItemEditor items={items} onChange={setItems} />
          </div>
          <Button type="submit" disabled={!propertyId}>
            Schedule inspection
          </Button>
        </form>
      </Card>

      <Card title="All inspections" className="mt-5">
        {inspections.length === 0 ? (
          <p className="text-sm text-muted">No inspections yet.</p>
        ) : (
          <ul className="space-y-4">
            {inspections.map((x) => (
              <li key={x.id} className="rounded-lg border border-border p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-sm text-text">
                    {TYPE_LABEL[x.type]} ·{" "}
                    <Badge tone={x.status === "completed" ? "success" : "brand"}>{x.status}</Badge> ·{" "}
                    {x.scheduled_for} · {addressOf(x.property_id)}
                  </span>
                  <div className="flex gap-2">
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => (editingId === x.id ? setEditingId(null) : startEdit(x))}
                    >
                      {editingId === x.id ? "Close" : "Edit"}
                    </Button>
                    <label className="cursor-pointer">
                      <span className="inline-flex h-8 items-center rounded-md border border-border px-3 text-sm text-text">
                        Add photo
                      </span>
                      <input
                        type="file"
                        accept="image/*"
                        className="hidden"
                        aria-label={`Add photo to inspection on ${x.scheduled_for}`}
                        onChange={(e) => onUpload(x.id, e.target.files?.[0])}
                      />
                    </label>
                    <Button variant="danger" size="sm" onClick={() => setDeletingId(x.id)}>
                      Delete
                    </Button>
                  </div>
                </div>

                {x.note ? <p className="mt-2 text-sm text-muted">{x.note}</p> : null}

                {x.items.length > 0 ? (
                  <ul className="mt-2 space-y-1 text-sm text-text">
                    {x.items.map((it) => (
                      <li key={it.id}>
                        {it.area} — <Badge tone={CONDITION_TONE[it.condition]}>{it.condition}</Badge>
                        {it.note ? ` — ${it.note}` : ""}
                      </li>
                    ))}
                  </ul>
                ) : null}

                {x.image_urls.length > 0 ? (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {x.image_urls.map((url) => (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        key={url}
                        src={`${API_BASE_URL}${url}`}
                        alt="Inspection photo"
                        className="h-20 w-20 rounded object-cover"
                      />
                    ))}
                  </div>
                ) : null}

                {editingId === x.id && editDraft ? (
                  <div className="mt-3 space-y-3 border-t border-border pt-3">
                    <div className="flex flex-wrap items-end gap-2">
                      <Select
                        aria-label="Edit status"
                        value={editDraft.status}
                        onChange={(e) =>
                          setEditDraft({
                            ...editDraft,
                            status: e.target.value as InspectionInfo["status"],
                          })
                        }
                        className="w-40"
                      >
                        <option value="scheduled">scheduled</option>
                        <option value="completed">completed</option>
                      </Select>
                      <Input
                        type="date"
                        aria-label="Edit date"
                        value={editDraft.scheduled_for}
                        onChange={(e) =>
                          setEditDraft({ ...editDraft, scheduled_for: e.target.value })
                        }
                        className="w-40"
                      />
                      <Input
                        type="text"
                        placeholder="Note (optional)"
                        aria-label="Edit note"
                        value={editDraft.note}
                        onChange={(e) => setEditDraft({ ...editDraft, note: e.target.value })}
                        className="flex-1"
                      />
                    </div>
                    <div>
                      <p className="mb-1 text-sm font-medium text-text">Checklist</p>
                      <ItemEditor
                        items={editDraft.items}
                        onChange={(next) => setEditDraft({ ...editDraft, items: next })}
                      />
                    </div>
                    <Button size="sm" onClick={() => saveEdit(x.id)}>
                      Save changes
                    </Button>
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </Card>

      <ConfirmDialog
        open={deletingId !== null}
        label="Delete inspection"
        message="Delete this inspection? This cannot be undone."
        confirmLabel="Yes, delete"
        onConfirm={() => deletingId && onDelete(deletingId)}
        onCancel={() => setDeletingId(null)}
      />
    </AppShell>
  );
}
