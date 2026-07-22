import type { ReactNode } from "react";

/** Centered card for the signed-out pages. Owns their <main>. */
export function AuthFrame({ title, children }: { title: string; children: ReactNode }) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-canvas p-6">
      <div className="w-full max-w-sm">
        <div className="mb-5 flex items-center justify-center gap-2">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand text-sm font-semibold text-white">
            R
          </span>
          <span className="text-lg font-semibold text-text">Rentals</span>
        </div>
        <div className="space-y-4 rounded-xl border border-border bg-surface p-6 shadow-[var(--shadow-card)]">
          <h1 className="text-xl font-semibold text-text">{title}</h1>
          {children}
        </div>
      </div>
    </main>
  );
}
