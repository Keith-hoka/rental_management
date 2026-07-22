import type { ReactNode } from "react";

export function DataList({ children }: { children: ReactNode }) {
  return (
    <ul className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface">
      {children}
    </ul>
  );
}

export function DataRow({ children }: { children: ReactNode }) {
  return <li className="p-4 text-sm text-text">{children}</li>;
}
