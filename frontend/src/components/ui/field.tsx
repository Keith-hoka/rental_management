import type { ReactNode } from "react";

/**
 * Label plus control. The label text is an accessible name the e2e suite queries,
 * so callers must pass it verbatim.
 */
export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-muted">{label}</span>
      {children}
    </label>
  );
}
