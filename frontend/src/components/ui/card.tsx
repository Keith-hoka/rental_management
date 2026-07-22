import type { ReactNode } from "react";

export function Card({
  title,
  actions,
  className = "",
  children,
}: {
  title?: string;
  actions?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section
      className={`rounded-xl border border-border bg-surface p-4 shadow-[var(--shadow-card)] ${className}`}
    >
      {(title || actions) && (
        <div className="mb-3 flex items-center justify-between gap-3">
          {title && <h2 className="font-semibold text-text">{title}</h2>}
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}
