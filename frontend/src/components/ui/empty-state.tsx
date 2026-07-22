import type { ReactNode } from "react";

export function EmptyState({ children }: { children: ReactNode }) {
  return (
    <p className="rounded-xl border border-dashed border-border p-6 text-center text-muted">
      {children}
    </p>
  );
}
