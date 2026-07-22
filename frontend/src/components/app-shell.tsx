"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";
import { ThemeToggle } from "@/components/ui";

const MANAGE = [
  { href: "/app", label: "Dashboard" },
  { href: "/app/properties", label: "Properties" },
  { href: "/app/leases", label: "Leases" },
  { href: "/app/tenants", label: "Tenants" },
  { href: "/app/payments", label: "Payments" },
  { href: "/app/maintenance", label: "Maintenance" },
  { href: "/app/messages", label: "Messages" },
  { href: "/app/team", label: "Team" },
];

const SETTINGS = [
  { href: "/app/profile", label: "Profile" },
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
  const [open, setOpen] = useState(false);
  const isActive = (href: string) =>
    href === "/app" ? pathname === "/app" : pathname.startsWith(href);

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <nav
        aria-label="Main"
        className="flex shrink-0 flex-col border-b border-border bg-surface p-3 md:w-60 md:border-r md:border-b-0"
      >
        <div className="flex items-center justify-between px-2 md:mb-4">
          <div className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand text-sm font-semibold text-white">
              R
            </span>
            <span className="font-semibold text-text">Rentals</span>
          </div>
          <button
            type="button"
            aria-label="Menu"
            aria-expanded={open}
            onClick={() => setOpen((wasOpen) => !wasOpen)}
            className="rounded-lg border border-strong p-1.5 text-text hover:bg-surface-2 md:hidden"
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
        </div>
        {/* md:flex-1 so the settings group's md:mt-auto still reaches the bottom.
            Tapping anything inside closes the menu, which on mobile is what a
            navigation should do. */}
        <div
          onClick={() => setOpen(false)}
          className={`${open ? "flex" : "hidden"} mt-4 flex-col md:mt-0 md:flex md:flex-1`}
        >
          <p className="px-3 pb-1 text-xs font-medium tracking-wide text-muted uppercase">
            Main menu
          </p>
          <div className="space-y-1">
          {MANAGE.map((item) => (
            <NavLink
              key={item.href}
              {...item}
              active={isActive(item.href)}
              badge={item.label === "Messages" ? unread : undefined}
            />
          ))}
          </div>
          {/* mt-auto bottom-anchors settings; mb keeps it clear of the very edge. */}
          <div className="mt-6 space-y-1 md:mt-auto md:mb-10 md:pt-6">
            <p className="px-3 pb-1 text-xs font-medium tracking-wide text-muted uppercase">
              Settings
            </p>
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
        </div>
      </nav>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-end gap-3 border-b border-border bg-surface px-6 py-3">
          <ThemeToggle />
          {/* Keeps data-testid="welcome" with both name and role: auth.spec
              asserts the element contains "E2E User (landlord)". */}
          <div data-testid="welcome" className="flex items-center gap-2 text-sm">
            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-brand-soft text-xs font-semibold text-brand-on-soft">
              {me.name.slice(0, 1).toUpperCase()}
            </span>
            <span className="text-text">
              {me.name} ({me.role})
            </span>
          </div>
        </header>
        <main className="min-w-0 flex-1 p-6">{children}</main>
      </div>
    </div>
  );
}
