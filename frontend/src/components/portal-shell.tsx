"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
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
  const isActive = (href: string) =>
    href === "/app" ? pathname === "/app" : pathname.startsWith(href);

  return (
    <div className="min-h-screen bg-canvas">
      <header className="border-b border-border bg-surface">
        <div className="mx-auto flex max-w-3xl flex-wrap items-center justify-between gap-3 px-6 py-3">
          {/* Same testid and shape as AppShell: auth.spec asserts this element
              contains both the name and the role. */}
          <div data-testid="welcome" className="flex items-center gap-2 text-sm">
            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-brand-soft text-xs font-semibold text-brand-on-soft">
              {me.name.slice(0, 1).toUpperCase()}
            </span>
            <span className="text-text">
              {me.name} ({me.role})
            </span>
          </div>
          <nav aria-label="Main" className="flex flex-wrap items-center gap-1">
            {LINKS.map((item) => (
              <NavLink
                key={item.href}
                {...item}
                active={isActive(item.href)}
                badge={item.label === "Messages" ? unread : undefined}
              />
            ))}
            <button onClick={onLogOut} className={QUIET}>
              Log out
            </button>
            {/* Same top-right corner as the manager header. */}
            <ThemeToggle className="ml-1" />
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-3xl p-6">{children}</main>
    </div>
  );
}
