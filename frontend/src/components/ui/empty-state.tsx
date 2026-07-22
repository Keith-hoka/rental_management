import type { ReactNode } from "react";

/**
 * Borderless on purpose: it usually sits inside a DataList that already sits
 * inside a Card, and a third frame around it just adds noise.
 */
export function EmptyState({ children }: { children: ReactNode }) {
  return <p className="p-6 text-center text-muted">{children}</p>;
}
