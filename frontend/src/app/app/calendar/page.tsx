"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  createEvent,
  deleteEvent,
  listCalendar,
  updateEvent,
  type CalendarEntry,
  type CalendarKind,
} from "@/lib/calendar";
import { listProperties, type Property } from "@/lib/properties";
import { AppShell } from "@/components/app-shell";
import { useShell } from "@/components/use-shell";
import {
  Button,
  Card,
  ConfirmDialog,
  Input,
  PageHeader,
  Select,
  Textarea,
} from "@/components/ui";

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

const KIND_TONE: Record<CalendarKind, string> = {
  lease_start: "bg-brand-soft text-brand-on-soft",
  lease_end: "bg-danger-soft text-danger-on-soft",
  rent_due: "bg-warning-soft text-warning-on-soft",
  maintenance: "bg-surface-2 text-muted",
  event: "bg-success-soft text-success-on-soft",
};

function ymd(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
    d.getDate(),
  ).padStart(2, "0")}`;
}

/** A datetime-local input value (local wall-clock) for a Date. */
function localInput(d: Date): string {
  return `${ymd(d)}T${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

/** The 42 days (6 weeks) of a month grid, starting on the Sunday of week one. */
function gridDays(year: number, month: number): Date[] {
  const first = new Date(year, month, 1);
  const start = new Date(year, month, 1 - first.getDay());
  return Array.from(
    { length: 42 },
    (_, i) => new Date(start.getFullYear(), start.getMonth(), start.getDate() + i),
  );
}

interface Span {
  entry: CalendarEntry;
  start: Date;
  end: Date;
  startYmd: string;
  endYmd: string;
}

/** An entry's inclusive day range: derived kinds are a single date; events span start_at..end_at. */
function toSpan(entry: CalendarEntry): Span {
  const start = entry.all_day
    ? new Date(`${entry.date}T00:00:00`)
    : new Date(entry.start_at as string);
  const end = entry.all_day
    ? new Date(`${entry.date}T00:00:00`)
    : new Date(entry.end_at as string);
  return { entry, start, end, startYmd: ymd(start), endYmd: ymd(end) };
}

export default function CalendarPage() {
  const { me, unread, logOut } = useShell();
  const router = useRouter();
  const [year, setYear] = useState(() => new Date().getFullYear());
  const [month, setMonth] = useState(() => new Date().getMonth());
  const [entries, setEntries] = useState<CalendarEntry[]>([]);
  const [properties, setProperties] = useState<Property[]>([]);

  // Event dialog state.
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [startLocal, setStartLocal] = useState("");
  const [endLocal, setEndLocal] = useState("");
  const [propertyId, setPropertyId] = useState("");
  const [confirmOpen, setConfirmOpen] = useState(false);

  async function refresh() {
    const days = gridDays(year, month);
    setEntries(await listCalendar(ymd(days[0]), ymd(days[41])));
  }

  useEffect(() => {
    if (!me) return;
    let active = true;
    const days = gridDays(year, month);
    listCalendar(ymd(days[0]), ymd(days[41]))
      .then((list) => active && setEntries(list))
      .catch(() => active && setEntries([]));
    return () => {
      active = false;
    };
  }, [me, year, month]);

  useEffect(() => {
    if (!me) return;
    listProperties()
      .then(setProperties)
      .catch(() => setProperties([]));
  }, [me]);

  if (!me) return null;

  const days = gridDays(year, month);
  const weeks = [0, 1, 2, 3, 4, 5].map((w) => days.slice(w * 7, w * 7 + 7));
  const spans = entries
    .map(toSpan)
    .sort((a, b) => (a.startYmd < b.startYmd ? -1 : a.startYmd > b.startYmd ? 1 : 0));

  const monthLabel = new Date(year, month, 1).toLocaleDateString(undefined, {
    month: "long",
    year: "numeric",
  });
  const todayKey = ymd(new Date());

  function shift(delta: number) {
    const d = new Date(year, month + delta, 1);
    setYear(d.getFullYear());
    setMonth(d.getMonth());
  }

  function goToday() {
    const d = new Date();
    setYear(d.getFullYear());
    setMonth(d.getMonth());
  }

  function openNew(day: Date) {
    setEditingId(null);
    setTitle("");
    setDescription("");
    const start = new Date(day.getFullYear(), day.getMonth(), day.getDate(), 9, 0);
    const end = new Date(day.getFullYear(), day.getMonth(), day.getDate(), 10, 0);
    setStartLocal(localInput(start));
    setEndLocal(localInput(end));
    setPropertyId("");
    setDialogOpen(true);
  }

  function openEdit(entry: CalendarEntry) {
    setEditingId(entry.event_id);
    setTitle(entry.title);
    setDescription(entry.description ?? "");
    setStartLocal(localInput(new Date(entry.start_at as string)));
    setEndLocal(localInput(new Date(entry.end_at as string)));
    setPropertyId(entry.property_id ?? "");
    setDialogOpen(true);
  }

  function onChipClick(entry: CalendarEntry) {
    if (entry.kind === "event") openEdit(entry);
    else if (entry.link) router.push(entry.link);
  }

  async function onSaveEvent() {
    const body = {
      title,
      description: description || null,
      start_at: new Date(startLocal).toISOString(),
      end_at: new Date(endLocal).toISOString(),
      property_id: propertyId || null,
    };
    if (editingId) await updateEvent(editingId, body);
    else await createEvent(body);
    setDialogOpen(false);
    await refresh();
  }

  async function onDeleteEvent() {
    if (editingId) await deleteEvent(editingId);
    setConfirmOpen(false);
    setDialogOpen(false);
    await refresh();
  }

  return (
    <AppShell me={me} unread={unread} onLogOut={logOut}>
      <PageHeader
        title="Calendar"
        actions={
          <span className="flex items-center gap-2">
            <Button variant="secondary" size="sm" onClick={() => shift(-1)}>
              Prev
            </Button>
            <Button variant="secondary" size="sm" onClick={goToday}>
              Today
            </Button>
            <Button variant="secondary" size="sm" onClick={() => shift(1)}>
              Next
            </Button>
            <Button size="sm" onClick={() => openNew(new Date())}>
              New event
            </Button>
          </span>
        }
      />
      <Card>
        <p className="mb-3 font-semibold text-text">{monthLabel}</p>
        <div className="grid grid-cols-7 gap-0.5 border-b border-border pb-1">
          {WEEKDAYS.map((w) => (
            <div key={w} className="px-1 text-xs font-medium text-muted">
              {w}
            </div>
          ))}
        </div>
        <div className="mt-1 space-y-1">
          {weeks.map((week, wi) => {
            const weekStart = ymd(week[0]);
            const weekEnd = ymd(week[6]);
            const bars = spans.filter((s) => s.startYmd <= weekEnd && s.endYmd >= weekStart);
            return (
              <div key={wi} className="rounded-lg border border-border p-1">
                <div className="grid grid-cols-7 gap-0.5">
                  {week.map((day) => {
                    const key = ymd(day);
                    const inMonth = day.getMonth() === month;
                    return (
                      <button
                        key={key}
                        type="button"
                        onClick={() => openNew(day)}
                        aria-label={`Add event on ${key}`}
                        className={`text-left text-xs ${
                          key === todayKey
                            ? "font-bold text-brand-fg"
                            : inMonth
                              ? "text-text"
                              : "text-muted"
                        }`}
                      >
                        {day.getDate()}
                      </button>
                    );
                  })}
                </div>
                <div className="mt-0.5 grid min-h-10 grid-cols-7 gap-0.5 content-start">
                  {bars.map((s, i) => {
                    const startCol = s.startYmd <= weekStart ? 0 : s.start.getDay();
                    const endCol = s.endYmd >= weekEnd ? 6 : s.end.getDay();
                    return (
                      <button
                        key={i}
                        type="button"
                        title={s.entry.title}
                        onClick={() => onChipClick(s.entry)}
                        style={{ gridColumn: `${startCol + 1} / span ${endCol - startCol + 1}` }}
                        className={`truncate rounded px-1 text-left text-xs ${KIND_TONE[s.entry.kind]}`}
                      >
                        {s.entry.title}
                      </button>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      </Card>

      {dialogOpen && (
        <div className="fixed inset-0 z-10 flex items-center justify-center bg-black/40 p-4">
          <div
            role="dialog"
            aria-modal="true"
            aria-label={editingId ? "Edit event" : "New event"}
            className="w-full max-w-sm rounded-xl border border-border bg-surface p-6 shadow-lg"
          >
            <div className="space-y-3">
              <label className="block text-sm text-muted">
                Title
                <Input value={title} onChange={(e) => setTitle(e.target.value)} />
              </label>
              <label className="block text-sm text-muted">
                Description
                <Textarea value={description} onChange={(e) => setDescription(e.target.value)} />
              </label>
              <label className="block text-sm text-muted">
                Start
                <Input
                  type="datetime-local"
                  value={startLocal}
                  onChange={(e) => setStartLocal(e.target.value)}
                />
              </label>
              <label className="block text-sm text-muted">
                End
                <Input
                  type="datetime-local"
                  value={endLocal}
                  onChange={(e) => setEndLocal(e.target.value)}
                />
              </label>
              <label className="block text-sm text-muted">
                Property
                <Select value={propertyId} onChange={(e) => setPropertyId(e.target.value)}>
                  <option value="">No property</option>
                  {properties.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.address}
                    </option>
                  ))}
                </Select>
              </label>
            </div>
            <div className="mt-5 flex justify-between gap-2">
              <span>
                {editingId && (
                  <Button variant="danger" size="sm" onClick={() => setConfirmOpen(true)}>
                    Delete
                  </Button>
                )}
              </span>
              <span className="flex gap-2">
                <Button variant="secondary" size="sm" onClick={() => setDialogOpen(false)}>
                  Cancel
                </Button>
                <Button
                  size="sm"
                  onClick={onSaveEvent}
                  disabled={!title || !startLocal || !endLocal}
                >
                  Save
                </Button>
              </span>
            </div>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={confirmOpen}
        label="Delete event"
        message="Delete this event? This cannot be undone."
        confirmLabel="Yes, delete"
        onConfirm={onDeleteEvent}
        onCancel={() => setConfirmOpen(false)}
      />
    </AppShell>
  );
}
