"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

const MANAGE = [
  { href: "/app", label: "Dashboard" },
  { href: "/app/properties", label: "Properties" },
  { href: "/app/leases", label: "Leases" },
  { href: "/app/maintenance", label: "Maintenance" },
  { href: "/app/messages", label: "Messages" },
  { href: "/app/team", label: "Team" },
];

const SETTINGS = [
  { href: "/app/profile", label: "Contact info" },
  { href: "/app/change-password", label: "Change password" },
];

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
  const tone = active
    ? "bg-brand-soft text-brand-on-soft"
    : "text-muted hover:bg-surface-2 hover:text-text";
  return (
    <Link
      href={href}
      className={`flex items-center rounded-lg px-3 py-2 text-sm font-medium ${tone}`}
    >
      {label}
      {badge ? (
        <span className="ml-auto rounded-full bg-brand px-2 py-0.5 text-xs text-white">{badge}</span>
      ) : null}
    </Link>
  );
}

export function AppShell({
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
    <div className="flex min-h-screen flex-col md:flex-row">
      <nav
        aria-label="Main"
        className="shrink-0 border-b border-border bg-surface p-3 md:w-60 md:border-r md:border-b-0"
      >
        <div className="mb-4 flex items-center gap-2 px-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand text-sm font-semibold text-white">
            R
          </span>
          <span className="font-semibold text-text">Rentals</span>
        </div>
        <p className="px-3 pb-1 text-xs font-medium tracking-wide text-muted uppercase">Manage</p>
        <div className="mb-4 space-y-1">
          {MANAGE.map((item) => (
            <NavLink
              key={item.href}
              {...item}
              active={isActive(item.href)}
              badge={item.label === "Messages" ? unread : undefined}
            />
          ))}
        </div>
        <p className="px-3 pb-1 text-xs font-medium tracking-wide text-muted uppercase">Settings</p>
        <div className="space-y-1">
          {SETTINGS.map((item) => (
            <NavLink key={item.href} {...item} active={isActive(item.href)} />
          ))}
          <button
            onClick={onLogOut}
            className="w-full rounded-lg px-3 py-2 text-left text-sm font-medium text-muted hover:bg-surface-2 hover:text-text"
          >
            Log out
          </button>
        </div>
      </nav>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="border-b border-border bg-surface px-6 py-3">
          <p data-testid="welcome" className="text-sm text-muted">
            Welcome, {me.name} ({me.role})
          </p>
        </header>
        <main className="min-w-0 flex-1 p-6">{children}</main>
      </div>
    </div>
  );
}
