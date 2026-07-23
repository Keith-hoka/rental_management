"use client";

import { useState } from "react";
import { exportPayments } from "@/lib/payments";
import { downloadBlob } from "@/lib/download";
import { Button, Input } from "@/components/ui";

/**
 * Export CSV control for the dashboard header: a button that opens a dialog
 * for a required date range, then downloads the payment history. Both dates
 * must be chosen before the download is allowed.
 */
export function PaymentExportButton() {
  const [open, setOpen] = useState(false);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");

  async function onDownload() {
    const blob = await exportPayments(from, to);
    downloadBlob(blob, "payment history.csv");
    setOpen(false);
  }

  return (
    <>
      <Button size="sm" onClick={() => setOpen(true)}>
        Export CSV
      </Button>
      {open && (
        <div className="fixed inset-0 z-10 flex items-center justify-center bg-black/40 p-4">
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Export payments"
            className="w-full max-w-sm rounded-xl border border-border bg-surface p-6 shadow-lg"
          >
            <p className="mb-4 text-text">Choose a date range to export the payment history.</p>
            <div className="mb-4 space-y-3">
              <label className="block">
                <span className="mb-1 block text-xs font-medium text-muted">Export from</span>
                <Input
                  type="date"
                  aria-label="Export from"
                  value={from}
                  onChange={(e) => setFrom(e.target.value)}
                />
              </label>
              <label className="block">
                <span className="mb-1 block text-xs font-medium text-muted">Export to</span>
                <Input
                  type="date"
                  aria-label="Export to"
                  value={to}
                  onChange={(e) => setTo(e.target.value)}
                />
              </label>
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="secondary" size="sm" onClick={() => setOpen(false)}>
                Cancel
              </Button>
              {/* Disabled until both dates are chosen: no range, no export. */}
              <Button size="sm" onClick={onDownload} disabled={!from || !to}>
                Download CSV
              </Button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
