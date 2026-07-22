"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";
import { ThemeToggle } from "@/components/ui";

const LINKS = [
  { href: "/app", label: "Dashboard" },
  { href: "/app/messages", label: "Messages" },
  { href: "/app/profile", label: "Profile" },
  { href: "/app/change-password", label: "Change password" },
];

const QUIET = "rounded-lg px-3 py-2 text-sm font-medium text-muted hover:bg-surface-2 hover:text-text";

function NavLink({
  href,
  label,
  active,
  badge,
}: {
  href: string;
  label: string;
  active: boolean;
  badge?: number;
}) {
  return (
    <Link
      href={href}
      className={`flex items-center gap-2 ${
        active ? "rounded-lg bg-brand-soft px-3 py-2 text-sm font-medium text-brand-on-soft" : QUIET
      }`}
    >
      {label}
      {badge ? (
        <span className="rounded-full bg-brand px-2 py-0.5 text-xs text-white">{badge}</span>
      ) : null}
    </Link>
  );
}

/**
 * Tenant chrome: one centred column with a top bar instead of the manager
 * sidebar, because a tenant has only their own lease to look at.
 */
export function PortalShell({
  me,
  unread,
  onLogOut,
  children,
}: {
  me: { name: string; role: string };
  unread: number;
  onLogOut: () => void;
  children: ReactNode;
}) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const isActive = (href: string) =>
    href === "/app" ? pathname === "/app" : pathname.startsWith(href);

  return (
    <div className="min-h-screen bg-canvas">
      {/* h-14 here and top-14 on the drawer are the same 3.5rem, as in AppShell:
          the fixed drawer has to be told where the bar ends. */}
      <header className="border-b border-border bg-surface">
        <div className="mx-auto flex h-14 max-w-3xl items-center gap-2 px-4 md:px-6">
          {/* Same testid and shape as AppShell: auth.spec asserts this element
              contains both the name and the role. */}
          <div data-testid="welcome" className="flex min-w-0 items-center gap-2 text-sm">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-soft text-xs font-semibold text-brand-on-soft">
              {me.name.slice(0, 1).toUpperCase()}
            </span>
            <span className="truncate text-text">
              {me.name} ({me.role})
            </span>
          </div>
          {/* Below md this is a fixed drawer that covers the page; from md it is
              the inline row it has always been. One <nav> either way, so the
              links never get a duplicate match under strict mode. */}
          <nav
            aria-label="Main"
            onClick={() => setOpen(false)}
            className={`${open ? "flex" : "hidden"} fixed inset-x-0 top-14 bottom-0 z-30 flex-col gap-1 overflow-y-auto border-border bg-surface p-3 shadow-lg md:static md:ml-auto md:flex md:flex-row md:items-center md:overflow-visible md:bg-transparent md:p-0 md:shadow-none`}
          >
            {LINKS.map((item) => (
              <NavLink
                key={item.href}
                {...item}
                active={isActive(item.href)}
                badge={item.label === "Messages" ? unread : undefined}
              />
            ))}
            <button onClick={onLogOut} className={`${QUIET} text-left`}>
              Log out
            </button>
          </nav>
          <button
            type="button"
            aria-label="Menu"
            aria-expanded={open}
            onClick={() => setOpen((wasOpen) => !wasOpen)}
            className="ml-auto shrink-0 rounded-lg border border-strong p-1.5 text-text hover:bg-surface-2 md:hidden"
          >
            <svg
              viewBox="0 0 24 24"
              width="18"
              height="18"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
            >
              <path d="M3 6h18M3 12h18M3 18h18" />
            </svg>
          </button>
          {/* Outside the nav so it stays reachable while the drawer is shut. */}
          <ThemeToggle className="shrink-0 md:ml-1" />
        </div>
      </header>
      <main className="mx-auto max-w-3xl p-6">{children}</main>
    </div>
  );
}
