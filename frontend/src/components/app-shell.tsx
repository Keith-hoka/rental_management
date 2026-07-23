"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { ThemeToggle } from "@/components/ui";

const MANAGE = [
  { href: "/app", label: "Dashboard" },
  { href: "/app/properties", label: "Properties" },
  { href: "/app/leases", label: "Leases" },
  { href: "/app/calendar", label: "Calendar" },
  { href: "/app/tenants", label: "Tenants" },
  { href: "/app/payments", label: "Payments" },
  { href: "/app/maintenance", label: "Maintenance" },
  { href: "/app/contractors", label: "Contractors" },
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
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const isActive = (href: string) =>
    href === "/app" ? pathname === "/app" : pathname.startsWith(href);

  // The drawer is fixed, so without this the page keeps scrolling underneath it.
  // On <html> because that is the scrolling element here; hiding body overflow
  // also works, but only via the rule that propagates it to the viewport when
  // the root is visible, which is a subtlety not worth depending on. A max-md:
  // class rather than an inline style keeps the breakpoint in CSS, so a resize
  // past md releases the lock on its own.
  useEffect(() => {
    document.documentElement.classList.toggle("max-md:overflow-hidden", open);
    return () => document.documentElement.classList.remove("max-md:overflow-hidden");
  }, [open]);

  return (
    // h-14 on the bar and top-14 on the drawer are the same 3.5rem: the drawer
    // is fixed, so it has to be told where the bar ends.
    <div className="flex min-h-screen flex-col md:h-dvh md:flex-row md:overflow-hidden">
      {/* Fixed drawer below md so opening it overlays the page instead of
          pushing it down; a static sidebar from md. Still one <nav>: a second
          copy would give every link a duplicate match under strict mode. */}
      <nav
        aria-label="Main"
        onClick={() => setOpen(false)}
        className={`${open ? "flex" : "hidden"} fixed inset-x-0 top-14 bottom-0 z-30 flex-col overflow-y-auto border-border bg-surface p-3 shadow-lg md:static md:flex md:w-60 md:shrink-0 md:overflow-y-auto md:border-r md:shadow-none`}
      >
        <div className="mb-4 hidden items-center gap-2 px-2 md:flex">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand text-sm font-semibold text-white">
            R
          </span>
          <span className="font-semibold text-text">Rentals</span>
        </div>
        <p className="px-3 pb-1 text-xs font-medium tracking-wide text-muted uppercase">Main menu</p>
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
      </nav>
      <div className="flex min-w-0 flex-1 flex-col md:overflow-hidden">
        <header className="sticky top-0 z-40 flex h-14 shrink-0 items-center gap-3 border-b border-border bg-surface px-4 md:static md:px-6">
          {/* Below md the brand and the menu button share this bar with the
              theme toggle and the user, so the app has a single top row. */}
          <div className="flex items-center gap-2 md:hidden">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand text-sm font-semibold text-white">
              R
            </span>
            {/* The mark carries the brand on the narrowest screens; the
                wordmark's width is what pushes the user's name onto two lines. */}
            <span className="hidden font-semibold text-text sm:inline">Rentals</span>
            <button
              type="button"
              aria-label="Menu"
              aria-expanded={open}
              onClick={() => setOpen((wasOpen) => !wasOpen)}
              className="ml-1 rounded-lg border border-strong p-1.5 text-text hover:bg-surface-2"
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
          <form
            className="hidden md:block"
            onSubmit={(e) => {
              e.preventDefault();
              const value = query.trim();
              if (value) router.push(`/app/search?q=${encodeURIComponent(value)}`);
            }}
          >
            <input
              type="search"
              aria-label="Search"
              placeholder="Search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="w-56 rounded-lg border border-strong bg-surface px-3 py-1.5 text-sm text-text placeholder:text-muted"
            />
          </form>
          <div className="ml-auto flex items-center gap-3">
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
          </div>
        </header>
        <main className="min-w-0 flex-1 p-6 md:overflow-y-auto">{children}</main>
      </div>
    </div>
  );
}
