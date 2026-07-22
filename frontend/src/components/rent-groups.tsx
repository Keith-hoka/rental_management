"use client";

import { useState } from "react";
import type { LeaseChargeGroup } from "@/lib/rent";
import { Badge, DataList, DataRow, EmptyState } from "@/components/ui";

function daysLate(oldestDue: string): number {
  const due = new Date(`${oldestDue}T00:00:00Z`);
  return Math.floor((Date.now() - due.getTime()) / 86_400_000);
}

/**
 * Lease rows for one rent bucket, each expandable to its charges. Several rows
 * can be open at once: chasing arrears means comparing tenants, not reading one.
 */
export function RentGroups({
  groups,
  empty,
  showDaysLate,
}: {
  groups: LeaseChargeGroup[];
  empty: string;
  showDaysLate: boolean;
}) {
  const [open, setOpen] = useState<Set<string>>(new Set());

  function toggle(leaseId: string) {
    setOpen((current) => {
      const next = new Set(current);
      if (next.has(leaseId)) next.delete(leaseId);
      else next.add(leaseId);
      return next;
    });
  }

  if (groups.length === 0) {
    return (
      <DataList>
        <DataRow>
          <EmptyState>{empty}</EmptyState>
        </DataRow>
      </DataList>
    );
  }

  return (
    <DataList>
      {groups.map((g) => (
        <DataRow key={g.lease_id}>
          <button
            type="button"
            // Per-row label: identical names on sibling rows break Playwright's
            // strict mode.
            aria-label={`Show charges for ${g.property_address}`}
            aria-expanded={open.has(g.lease_id)}
            onClick={() => toggle(g.lease_id)}
            className="flex w-full flex-wrap items-center justify-between gap-2 text-left"
          >
            <span className="min-w-0">
              <span className="font-medium text-text">{g.property_address}</span>
              <span className="text-muted"> · {g.tenant_name}</span>
            </span>
            <span className="flex items-center gap-2">
              {showDaysLate ? (
                <Badge tone="danger">{daysLate(g.oldest_due)} days late</Badge>
              ) : (
                <span className="text-xs text-muted">due {g.oldest_due}</span>
              )}
              <span className="font-medium text-text">${Number(g.total).toFixed(2)}</span>
            </span>
          </button>
          {open.has(g.lease_id) && (
            <ul className="mt-2 space-y-1 border-t border-border pt-2 text-xs text-muted">
              {g.charges.map((c) => (
                <li key={c.id} className="flex justify-between gap-2">
                  <span>
                    {c.period_start} to {c.period_end} · due {c.due_date}
                  </span>
                  <span>
                    ${Number(c.amount_paid).toFixed(2)} of ${Number(c.amount_due).toFixed(2)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </DataRow>
      ))}
    </DataList>
  );
}
