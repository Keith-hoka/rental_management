"use client";

import { useEffect, useState } from "react";
import { listCalendar, type CalendarEntry, type CalendarKind } from "@/lib/calendar";
import { AppShell } from "@/components/app-shell";
import { useShell } from "@/components/use-shell";
import { Button, Card, PageHeader } from "@/components/ui";

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

/** The 42 days (6 weeks) of a month grid, starting on the Sunday of week one. */
function gridDays(year: number, month: number): Date[] {
  const first = new Date(year, month, 1);
  const start = new Date(year, month, 1 - first.getDay());
  return Array.from(
    { length: 42 },
    (_, i) => new Date(start.getFullYear(), start.getMonth(), start.getDate() + i),
  );
}

function entryKey(entry: CalendarEntry): string {
  return entry.all_day ? (entry.date as string) : ymd(new Date(entry.start_at as string));
}

export default function CalendarPage() {
  const { me, unread, logOut } = useShell();
  const [year, setYear] = useState(() => new Date().getFullYear());
  const [month, setMonth] = useState(() => new Date().getMonth());
  const [entries, setEntries] = useState<CalendarEntry[]>([]);

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

  if (!me) return null;

  const days = gridDays(year, month);
  const byDay = new Map<string, CalendarEntry[]>();
  for (const e of entries) {
    const key = entryKey(e);
    const list = byDay.get(key);
    if (list) list.push(e);
    else byDay.set(key, [e]);
  }

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
          </span>
        }
      />
      <Card>
        <p className="mb-3 font-semibold text-text">{monthLabel}</p>
        <div className="grid grid-cols-7 gap-1">
          {WEEKDAYS.map((w) => (
            <div key={w} className="px-1 pb-1 text-xs font-medium text-muted">
              {w}
            </div>
          ))}
          {days.map((day) => {
            const key = ymd(day);
            const inMonth = day.getMonth() === month;
            const dayEntries = byDay.get(key) ?? [];
            return (
              <div
                key={key}
                className={`min-h-24 rounded-lg border border-border p-1 ${
                  inMonth ? "bg-surface" : "bg-surface-2"
                }`}
              >
                <div
                  className={`text-xs ${
                    key === todayKey
                      ? "font-bold text-brand-fg"
                      : inMonth
                        ? "text-text"
                        : "text-muted"
                  }`}
                >
                  {day.getDate()}
                </div>
                <div className="mt-0.5 space-y-0.5">
                  {dayEntries.map((e, i) => (
                    <span
                      key={i}
                      title={e.title}
                      className={`block truncate rounded px-1 text-xs ${KIND_TONE[e.kind]}`}
                    >
                      {e.title}
                    </span>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </Card>
    </AppShell>
  );
}
