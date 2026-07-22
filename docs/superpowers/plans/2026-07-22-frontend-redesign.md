# Frontend Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace hand-rolled utility markup across all 20 pages with an indigo design system: semantic tokens, a shared component library, a sidebar shell for managers, a single-column shell for tenants, and a working dark mode.

**Architecture:** Tokens in `globals.css` (light + dark values for the same variable names) → components in `src/components/ui/` that consume only those tokens → shells that own the page chrome. No component ever writes a `dark:` variant; dark mode is one override block.

**Tech Stack:** Next.js 16.2.10 App Router, React 19, Tailwind v4 CSS-first `@theme`, Recharts 3.10. No new dependencies.

## Global Constraints

- No emojis in code.
- One component per file; pages import from `@/components/ui`.
- Frontend checks from `frontend/`: `npm run lint`, `npm run build`, `npx playwright test --workers=1`.
- Backend ruff sequence before every push, from `backend/`:
  `uv run ruff format .` -> `uv run ruff check --fix .` -> `uv run ruff check .` -> `uv run ruff format --check .`
- Each task ends with: lint + build + affected e2e -> ruff -> commit -> `git push` -> report -> WAIT for approval.
- **Never change a user-visible accessible name.** The 13 e2e specs pin the interface by placeholder,
  label, button/heading/link name, test id and alt text. The full list is in the spec's "Preserved
  Accessible Names" section. When markup moves, the text moves with it verbatim.
- e2e needs a running backend on port 8000. Start it with the scheduler off:
  `REMINDERS_ENABLED=false uv run uvicorn app.main:app --port 8000` (the dev `.env` reaches Resend for real).
- Playwright's dev server reuses an existing one; restart `npm run dev` after changing `globals.css`
  or `layout.tsx` if styles look stale.

## Conversion Rules (apply in every page task)

These replace the repeated utility strings. Learn them once; each page task references them.

| Existing markup | Becomes |
| --- | --- |
| `<main className="mx-auto max-w-* p-8">` | deleted — the shell owns `<main>`; the page returns a fragment |
| `<h1 className="text-2xl font-semibold">X</h1>` | `<PageHeader title="X" />` (still renders `<h1>X</h1>`) |
| `<button className="rounded bg-blue-600 px-3 py-2 text-white">` | `<Button>` |
| `<button className="... text-red-600">` | `<Button variant="danger">` |
| `<button className="rounded border px-3 py-1">` | `<Button variant="secondary">` |
| `<Link className="rounded border px-3 py-1 text-blue-600">` | `<Link className={linkButton}>` from `@/components/ui` |
| `<li className="rounded border p-3">` | `<Card>` or a `DataList` row |
| `<input className="rounded border px-2 py-1">` | `<Input>` |
| `<select className="rounded border px-2 py-1">` | `<Select>` |
| bare status text (`paid`, `overdue`, `open`) | `<Badge tone={...}>` |
| `<li className="text-gray-500">No … yet.</li>` | `<EmptyState>No … yet.</EmptyState>` |
| `text-gray-500` / `text-gray-600` | `text-muted` |
| `text-gray-800` / `text-gray-900` | `text-text` |
| `border` / `border-gray-*` | `border-border` |
| `bg-white` | `bg-surface` |

**Page files keep `"use client"`, all hooks, all data fetching and all strings unchanged.** These
tasks are markup substitution only — no behavior edits.

---

## Task Overview

1. Tokens, `globals.css`, font fix, metadata
2. Component library
3. `AppShell` + sidebar + strict-mode fix + manager dashboard
4. Marketing and auth pages
5. Properties pages
6. Leases pages
7. Maintenance, Messages, Team
8. Profile, change-password, tenant `PortalShell`
9. `ThemeToggle`, dark-mode pass, full e2e

---

### Task 1: Tokens, globals.css, font fix, metadata

**Files:**
- Modify: `frontend/src/app/globals.css`
- Modify: `frontend/src/app/layout.tsx`

**Interfaces:**
- Produces: Tailwind utilities `bg-canvas`, `bg-surface`, `bg-surface-2`, `border-border`,
  `text-text`, `text-muted`, `bg-brand`, `text-brand`, `bg-brand-soft`, `text-brand-on-soft`, and
  the same `-soft` / `-on-soft` triples for `success`, `warning`, `danger`; plus the raw CSS vars
  (e.g. `var(--color-brand)`) for SVG fills.

- [ ] **Step 1: Replace globals.css**

Replace the whole of `frontend/src/app/globals.css`:

```css
@import "tailwindcss";

:root {
  --color-canvas: #f6f7fb;
  --color-surface: #ffffff;
  --color-surface-2: #f1f2f7;
  --color-border: #e6e8f0;
  --color-text: #12141c;
  --color-muted: #6b7280;
  --color-brand: #4f46e5;
  --color-brand-hover: #4338ca;
  --color-brand-soft: #eef2ff;
  --color-brand-on-soft: #3730a3;
  --color-success: #16a34a;
  --color-success-soft: #dcfce7;
  --color-success-on-soft: #14532d;
  --color-warning: #d97706;
  --color-warning-soft: #fef3c7;
  --color-warning-on-soft: #78350f;
  --color-danger: #dc2626;
  --color-danger-soft: #fee2e2;
  --color-danger-on-soft: #7f1d1d;
  --shadow-card: 0 1px 2px rgb(16 20 40 / 0.04), 0 4px 12px rgb(16 20 40 / 0.06);
}

/* Dark values for the same names: components never write a dark: variant. */
:root[data-theme="dark"] {
  --color-canvas: #0f1117;
  --color-surface: #171a23;
  --color-surface-2: #1f2330;
  --color-border: #262a36;
  --color-text: #e8eaf0;
  --color-muted: #9ba1b0;
  --color-brand: #6366f1;
  --color-brand-hover: #818cf8;
  --color-brand-soft: #242943;
  --color-brand-on-soft: #c7d2fe;
  --color-success: #4ade80;
  --color-success-soft: #14532d;
  --color-success-on-soft: #bbf7d0;
  --color-warning: #fbbf24;
  --color-warning-soft: #78350f;
  --color-warning-on-soft: #fde68a;
  --color-danger: #f87171;
  --color-danger-soft: #7f1d1d;
  --color-danger-on-soft: #fecaca;
  --shadow-card: none;
}

@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --color-canvas: #0f1117;
    --color-surface: #171a23;
    --color-surface-2: #1f2330;
    --color-border: #262a36;
    --color-text: #e8eaf0;
    --color-muted: #9ba1b0;
    --color-brand: #6366f1;
    --color-brand-hover: #818cf8;
    --color-brand-soft: #242943;
    --color-brand-on-soft: #c7d2fe;
    --color-success: #4ade80;
    --color-success-soft: #14532d;
    --color-success-on-soft: #bbf7d0;
    --color-warning: #fbbf24;
    --color-warning-soft: #78350f;
    --color-warning-on-soft: #fde68a;
    --color-danger: #f87171;
    --color-danger-soft: #7f1d1d;
    --color-danger-on-soft: #fecaca;
    --shadow-card: none;
  }
}

@theme inline {
  --color-canvas: var(--color-canvas);
  --color-surface: var(--color-surface);
  --color-surface-2: var(--color-surface-2);
  --color-border: var(--color-border);
  --color-text: var(--color-text);
  --color-muted: var(--color-muted);
  --color-brand: var(--color-brand);
  --color-brand-hover: var(--color-brand-hover);
  --color-brand-soft: var(--color-brand-soft);
  --color-brand-on-soft: var(--color-brand-on-soft);
  --color-success: var(--color-success);
  --color-success-soft: var(--color-success-soft);
  --color-success-on-soft: var(--color-success-on-soft);
  --color-warning: var(--color-warning);
  --color-warning-soft: var(--color-warning-soft);
  --color-warning-on-soft: var(--color-warning-on-soft);
  --color-danger: var(--color-danger);
  --color-danger-soft: var(--color-danger-soft);
  --color-danger-on-soft: var(--color-danger-on-soft);
  --font-sans: var(--font-geist-sans);
  --font-mono: var(--font-geist-mono);
}

body {
  background: var(--color-canvas);
  color: var(--color-text);
  font-family: var(--font-geist-sans), system-ui, sans-serif;
}
```

The old file set `font-family: Arial` on `body`, which overrode the Geist font the layout loads — the
app has never rendered in Geist. It also had a `prefers-color-scheme` block that flipped only
background and foreground, leaving cards and text colors light, which is why dark mode looked broken.

- [ ] **Step 2: Update the layout metadata and color-scheme**

In `frontend/src/app/layout.tsx`, replace the `metadata` export:

```tsx
export const metadata: Metadata = {
  title: "Rental Management",
  description: "Manage properties, leases, rent and maintenance in one place.",
};
```

and add the color-scheme meta inside the `<html>` element, before `<body>`:

```tsx
      <head>
        <meta name="color-scheme" content="light dark" />
      </head>
```

- [ ] **Step 3: Verify**

```bash
cd frontend && npm run lint && npm run build
```
Expected: clean. Nothing looks different yet — no page consumes the tokens.

- [ ] **Step 4: Commit and push**

```bash
git add frontend/src/app/globals.css frontend/src/app/layout.tsx
git commit -m "Add design tokens, fix the overridden font and the default metadata"
git push
```
Then report and wait for approval.

---

### Task 2: Component library

**Files:**
- Create: `frontend/src/components/ui/button.tsx`, `card.tsx`, `stat-card.tsx`, `field.tsx`,
  `input.tsx`, `badge.tsx`, `page-header.tsx`, `empty-state.tsx`, `data-list.tsx`, `index.ts`

**Interfaces:**
- Produces, all from `@/components/ui`: `Button`, `linkButton`, `Card`, `StatCard`, `Field`,
  `Input`, `Select`, `Textarea`, `Badge`, `PageHeader`, `EmptyState`, `DataList`, `DataRow`.

- [ ] **Step 1: Button**

Create `frontend/src/components/ui/button.tsx`:

```tsx
import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-brand text-white hover:bg-brand-hover",
  secondary: "border border-border bg-surface text-text hover:bg-surface-2",
  ghost: "text-brand hover:bg-brand-soft",
  danger: "border border-border bg-surface text-danger hover:bg-danger-soft",
};

const BASE =
  "inline-flex items-center justify-center gap-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50";

/** Shared classes for a Link that should look like a secondary button. */
export const linkButton = `${BASE} ${VARIANTS.secondary} px-3 py-2`;

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: "sm" | "md";
}

export function Button({ variant = "primary", size = "md", className = "", ...rest }: Props) {
  const sizing = size === "sm" ? "px-2.5 py-1.5 text-xs" : "px-3 py-2";
  return <button className={`${BASE} ${VARIANTS[variant]} ${sizing} ${className}`} {...rest} />;
}
```

- [ ] **Step 2: Card, StatCard, PageHeader, EmptyState**

Create `frontend/src/components/ui/card.tsx`:

```tsx
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
```

Create `frontend/src/components/ui/stat-card.tsx`:

```tsx
export function StatCard({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: string;
  tone?: "default" | "danger";
}) {
  return (
    <div className="rounded-xl border border-border bg-surface p-4 shadow-[var(--shadow-card)]">
      <p className="text-xs text-muted">{label}</p>
      <p
        className={`mt-1 text-xl font-semibold ${tone === "danger" ? "text-danger" : "text-text"}`}
      >
        {value}
      </p>
    </div>
  );
}
```

Create `frontend/src/components/ui/page-header.tsx`:

```tsx
import type { ReactNode } from "react";

export function PageHeader({ title, actions }: { title: string; actions?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
      <h1 className="text-2xl font-semibold text-text">{title}</h1>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}
```

Create `frontend/src/components/ui/empty-state.tsx`:

```tsx
import type { ReactNode } from "react";

export function EmptyState({ children }: { children: ReactNode }) {
  return <p className="rounded-xl border border-dashed border-border p-6 text-center text-muted">{children}</p>;
}
```

- [ ] **Step 3: Field, Input, Select, Textarea**

Create `frontend/src/components/ui/input.tsx`:

```tsx
import type { InputHTMLAttributes, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";

const CONTROL =
  "w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text placeholder:text-muted focus:border-brand focus:outline-none";

export function Input({ className = "", ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={`${CONTROL} ${className}`} {...rest} />;
}

export function Select({ className = "", ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={`${CONTROL} ${className}`} {...rest} />;
}

export function Textarea({ className = "", ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={`${CONTROL} ${className}`} {...rest} />;
}
```

Create `frontend/src/components/ui/field.tsx`:

```tsx
import type { ReactNode } from "react";

/**
 * Label plus control. The label text is an accessible name the e2e suite queries,
 * so callers must pass it verbatim.
 */
export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-muted">{label}</span>
      {children}
    </label>
  );
}
```

- [ ] **Step 4: Badge and DataList**

Create `frontend/src/components/ui/badge.tsx`:

```tsx
import type { ReactNode } from "react";

type Tone = "neutral" | "brand" | "success" | "warning" | "danger";

const TONES: Record<Tone, string> = {
  neutral: "bg-surface-2 text-muted",
  brand: "bg-brand-soft text-brand-on-soft",
  success: "bg-success-soft text-success-on-soft",
  warning: "bg-warning-soft text-warning-on-soft",
  danger: "bg-danger-soft text-danger-on-soft",
};

export function Badge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${TONES[tone]}`}>
      {children}
    </span>
  );
}
```

Create `frontend/src/components/ui/data-list.tsx`:

```tsx
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
```

- [ ] **Step 5: Barrel export**

Create `frontend/src/components/ui/index.ts`:

```ts
export { Button, linkButton } from "./button";
export { Card } from "./card";
export { StatCard } from "./stat-card";
export { Field } from "./field";
export { Input, Select, Textarea } from "./input";
export { Badge } from "./badge";
export { PageHeader } from "./page-header";
export { EmptyState } from "./empty-state";
export { DataList, DataRow } from "./data-list";
```

- [ ] **Step 6: Verify**

```bash
cd frontend && npm run lint && npm run build
```
Expected: clean. No page imports these yet, so the build proves only that they compile.

- [ ] **Step 7: Commit and push**

```bash
git add frontend/src/components/ui
git commit -m "Add the shared UI component library"
git push
```
Then report and wait for approval.

---

### Task 3: AppShell, sidebar, strict-mode fix, manager dashboard

**Files:**
- Create: `frontend/src/components/app-shell.tsx`
- Modify: `frontend/src/app/app/page.tsx`
- Modify: `frontend/e2e/leases.spec.ts`

**Interfaces:**
- Consumes: `Button`, `linkButton`, `Card`, `StatCard`, `PageHeader` (Task 2); tokens (Task 1);
  `getUnreadCount` from `@/lib/notifications`.
- Produces: `AppShell` — props `{ me: { name: string; role: string }, unread: number, onLogOut: () => void, children: ReactNode }`. It renders `<nav aria-label="Main">` and the page's only `<main>`.

- [ ] **Step 1: Create AppShell**

Create `frontend/src/components/app-shell.tsx`:

```tsx
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

function NavLink({ href, label, active, badge }: { href: string; label: string; active: boolean; badge?: number }) {
  const tone = active ? "bg-brand-soft text-brand-on-soft" : "text-muted hover:bg-surface-2 hover:text-text";
  return (
    <Link href={href} className={`flex items-center rounded-lg px-3 py-2 text-sm font-medium ${tone}`}>
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
  const isActive = (href: string) => (href === "/app" ? pathname === "/app" : pathname.startsWith(href));

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <nav
        aria-label="Main"
        className="shrink-0 border-b border-border bg-surface p-3 md:w-60 md:border-b-0 md:border-r"
      >
        <div className="mb-4 flex items-center gap-2 px-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand text-sm font-semibold text-white">
            R
          </span>
          <span className="font-semibold text-text">Rentals</span>
        </div>
        <p className="px-3 pb-1 text-xs font-medium uppercase tracking-wide text-muted">Manage</p>
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
        <p className="px-3 pb-1 text-xs font-medium uppercase tracking-wide text-muted">Settings</p>
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
```

`data-testid="welcome"` moves here from the dashboard body, keeping the exact text
`Welcome, {name} ({role})` that `auth.spec.ts` and others assert.

- [ ] **Step 2: Rewrite the manager branch of the dashboard**

In `frontend/src/app/app/page.tsx`:

1. Add the imports: `import { AppShell } from "@/components/app-shell";` and
   `import { Card, PageHeader, StatCard } from "@/components/ui";`
2. Delete the manager branch's `<div className="mt-4 flex gap-3">` nav row entirely — Properties,
   Leases, Maintenance, Team, Messages, Change password, Contact info and Log out now live in the
   sidebar. Keep `logOut` as the function passed to `AppShell`.
3. Delete the manager branch's `<p data-testid="welcome">` — the shell renders it.
4. Return the manager branch as:

```tsx
  return (
    <AppShell me={me} unread={unread} onLogOut={logOut}>
      <PageHeader title="Dashboard" />
      {stats && (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <StatCard label="Outstanding" value={`$${stats.outstanding}`} />
            <StatCard label="Overdue" value={`$${stats.overdue}`} tone="danger" />
            <StatCard label="Collected this month" value={`$${stats.collected_this_month}`} />
            <StatCard
              label="Properties"
              value={`${stats.properties_occupied} of ${stats.properties_total} occupied`}
            />
            <StatCard label="Active leases" value={String(stats.active_leases)} />
            <StatCard label="Tenants" value={String(stats.tenants)} />
          </div>
          <Card title="Monthly income" className="mt-5">
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={stats.monthly_income}>
                <XAxis dataKey="month" stroke="var(--color-muted)" fontSize={12} />
                <YAxis stroke="var(--color-muted)" fontSize={12} />
                <Tooltip
                  contentStyle={{
                    background: "var(--color-surface)",
                    border: "1px solid var(--color-border)",
                    borderRadius: 12,
                    color: "var(--color-text)",
                  }}
                />
                <Bar dataKey="amount" fill="var(--color-brand)" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </Card>
        </>
      )}
    </AppShell>
  );
```

`Card title="Monthly income"` renders `<h2>Monthly income</h2>`, preserving the heading
`dashboard-stats.spec.ts` asserts. `fill="var(--color-brand)"` makes the bars follow the theme —
SVG `fill` resolves CSS custom properties, so no JS is needed.

Leave the tenant branch untouched in this task; Task 8 converts it.

- [ ] **Step 3: Fix the strict-mode collision**

The sidebar now renders a "Leases" link on every manager page, including `/app/properties`, which
already has a per-row "Leases" shortcut. In `frontend/e2e/leases.spec.ts`, the assertion that runs
while on `/app/properties` (the one preceded by the comment about the per-row shortcut,
`await page.goto("/app/properties")`) becomes:

```ts
  await page.getByRole("main").getByRole("link", { name: "Leases" }).click();
```

Leave the two `/app` dashboard usages alone: those links moved into the sidebar, so each still has
exactly one match on that page.

- [ ] **Step 4: Verify**

```bash
cd frontend && npm run lint && npm run build
```
Start the backend if it is not running, then:
```bash
npx playwright test leases dashboard-stats auth --workers=1
```
Expected: all pass. If a "Leases" locator reports a strict-mode violation, the page it ran on has
another duplicate — scope that assertion to `getByRole("main")` the same way.

- [ ] **Step 5: Look at it**

Open `http://localhost:3000/app` and confirm the sidebar, stat cards and chart render as intended
before the remaining pages adopt the shell. Report what it looks like and wait for approval — this
is the review point for the whole redesign.

- [ ] **Step 6: Commit and push**

```bash
git add frontend/src/components/app-shell.tsx frontend/src/app/app/page.tsx frontend/e2e/leases.spec.ts
git commit -m "Add the manager app shell and restyle the dashboard"
git push
```
Then report and wait for approval.

---

### Task 4: Marketing and auth pages

**Files:**
- Modify: `frontend/src/app/page.tsx`, `login/page.tsx`, `signup/page.tsx`,
  `forgot-password/page.tsx`, `reset-password/page.tsx`, `accept-invite/page.tsx`

**Interfaces:**
- Consumes: `Button`, `Card`, `Field`, `Input`, `PageHeader` (Task 2).

- [ ] **Step 1: Build the shared auth frame**

Create `frontend/src/components/auth-frame.tsx`:

```tsx
import type { ReactNode } from "react";

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
        <div className="rounded-xl border border-border bg-surface p-6 shadow-[var(--shadow-card)]">
          <h1 className="mb-4 text-xl font-semibold text-text">{title}</h1>
          {children}
        </div>
      </div>
    </main>
  );
}
```

These pages sit outside `AppShell`, so `AuthFrame` owns their `<main>`.

- [ ] **Step 2: Convert each auth page**

For `login`, `signup`, `forgot-password`, `reset-password` and `accept-invite`: replace the outer
`<main>` and heading with `<AuthFrame title="...">` using the page's existing heading text, wrap each
input in `<Field label="...">` only where the page already had a visible label, swap `<input>` for
`<Input>` and the submit `<button>` for `<Button type="submit" className="w-full">`.

**Every placeholder string stays byte-identical**: `Your name`, `Organization name`, `Email`,
`Password (min 8 chars)`, `Password`, `New password (min 8 chars)`. Every button name stays: `Sign up`,
`Log in`, `Send reset link`, `Update password`. The `Forgot password?` link keeps its text.

Error and success messages keep their current strings; restyle them as
`<p className="text-sm text-danger">` and `<p className="text-sm text-success">`.

- [ ] **Step 3: Convert the marketing page**

`frontend/src/app/page.tsx` becomes a centered hero: product name, one line of description, a
primary `Link` to `/signup` styled with `bg-brand text-white` and a secondary `Link` to `/login`
using `linkButton`. Keep any link text the specs rely on.

- [ ] **Step 4: Verify**

```bash
cd frontend && npm run lint && npm run build
npx playwright test auth forgot-password change-password team-invitations --workers=1
```
Expected: all pass.

- [ ] **Step 5: Commit and push**

```bash
git add frontend/src/components/auth-frame.tsx frontend/src/app/page.tsx frontend/src/app/login frontend/src/app/signup frontend/src/app/forgot-password frontend/src/app/reset-password frontend/src/app/accept-invite
git commit -m "Restyle the marketing and auth pages"
git push
```
Then report and wait for approval.

---

### Task 5: Properties pages

**Files:**
- Modify: `frontend/src/app/app/properties/page.tsx`, `new/page.tsx`, `[id]/page.tsx`,
  `[id]/leases/page.tsx`

**Interfaces:**
- Consumes: `AppShell` (Task 3) and the component library.

- [ ] **Step 1: Give these pages the shell**

Each page currently renders its own `<main>` and fetches nothing about the user. To sit inside
`AppShell` they need `me` and `unread`. Add to each page the same `/auth/me` + `getUnreadCount()`
effect the dashboard uses, then return `<AppShell me={me} unread={unread} onLogOut={logOut}>…</AppShell>`
with the page's own content as children, and delete the page's `<main>` wrapper.

To avoid repeating that effect five times, create `frontend/src/components/use-shell.ts`:

```ts
"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { clearTokens, getAccessToken } from "@/lib/auth";
import { getUnreadCount } from "@/lib/notifications";

export interface Me {
  email: string;
  name: string;
  role: string;
}

/** Auth guard plus the data the shells need: the current user and the unread count. */
export function useShell() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [unread, setUnread] = useState(0);

  useEffect(() => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    let active = true;
    apiFetch<Me>("/api/v1/auth/me")
      .then((m) => {
        if (!active) return;
        setMe(m);
        getUnreadCount()
          .then((u) => active && setUnread(u.count))
          .catch(() => active && setUnread(0));
      })
      .catch(() => {
        clearTokens();
        router.replace("/login");
      });
    return () => {
      active = false;
    };
  }, [router]);

  function logOut() {
    clearTokens();
    router.replace("/login");
  }

  return { me, unread, logOut };
}
```

- [ ] **Step 2: Convert the list page**

`properties/page.tsx`: `<PageHeader title="Properties" actions={<Link href="/app/properties/new" className={linkButton}>New property</Link>} />`,
rows as `DataList` / `DataRow` with the address `Link`, a status `Badge`
(`vacant` -> `tone="warning"`, `occupied` -> `tone="success"`), and the per-row `Leases` link kept
verbatim. Empty state uses `EmptyState`. Delete the "Back to dashboard" link — the sidebar replaces it.

- [ ] **Step 3: Convert new, detail and property-leases pages**

`properties/new/page.tsx`: `<Card>` wrapping the form, `Field` + `Input` / `Select` per row, submit
as `<Button type="submit">Create property</Button>`. Labels `Bedrooms`, `Upload image` and the
placeholder `Address` (exact) stay verbatim.

`properties/[id]/page.tsx`: `PageHeader` with the address, image strip, an edit form in a `Card`,
`Edit` / `Save` / `Delete property` / `Yes, delete` buttons keep their names — `Delete property` and
`Yes, delete` become `variant="danger"`. Keep `alt="Property"` on images.

`properties/[id]/leases/page.tsx`: `PageHeader title="Leases"`, lease rows in a `DataList`, and keep
the existing "Back to properties" link.

- [ ] **Step 4: Verify**

```bash
cd frontend && npm run lint && npm run build
npx playwright test properties property-images leases --workers=1
```
Expected: all pass.

- [ ] **Step 5: Commit and push**

```bash
git add frontend/src/components/use-shell.ts frontend/src/app/app/properties
git commit -m "Restyle the properties pages onto the app shell"
git push
```
Then report and wait for approval.

---

### Task 6: Leases pages

**Files:**
- Modify: `frontend/src/app/app/leases/page.tsx`, `new/page.tsx`, `[leaseId]/page.tsx`,
  `TenantFields.tsx`

**Interfaces:**
- Consumes: `useShell` (Task 5), `AppShell`, the component library.

- [ ] **Step 1: List and new**

`leases/page.tsx`: `useShell` + `AppShell`, `<PageHeader title="Leases" actions={<Link href="/app/leases/new" className={linkButton}>New lease</Link>} />`,
rows in `DataList` with the property address link, dates, rent and a state `Badge`
(`active` -> `success`, `upcoming` -> `brand`, `ended` -> `neutral`). Keep the text `active` exactly —
`leases.spec.ts` asserts `getByText("active")`.

`leases/new/page.tsx`: the form in `Card`s — one for the property and dates, one for tenant details.
Labels `Property`, `Rent`, `Start`, `End`, `Bond (optional)`, `Notice period (days)` and the button
`Add lease` stay verbatim.

- [ ] **Step 2: TenantFields**

Convert `TenantFields.tsx` to `Field` + `Input`. The labels `Co-tenant 1 name`, `Co-tenant 1 email`,
`Co-tenant 1 phone`, the placeholders `Tenant name`, `Tenant email`, `Tenant phone (optional)` and
the button `Add co-tenant` all stay verbatim — several are indexed, so keep the index interpolation
exactly as it is.

- [ ] **Step 3: Lease detail**

`leases/[leaseId]/page.tsx` is the largest page. Wrap it in `AppShell` and give each existing
section its own `Card`, keeping the section headings that the specs assert:
`Rent charges`, `Expiry reminders`. Sections: lease summary, tenant roster, tenants and invitations,
payments (with the `Amount`, `Payment date` fields and the `Record payment` button), rent charges
(status `Badge`: `paid` -> success, `partial` -> warning, `unpaid` -> neutral, overdue -> danger),
expiry reminders. Keep `Invite`, `Revoke`, `Delete`, `Yes, delete`, `Edit`, `Save` verbatim.

- [ ] **Step 4: Verify**

```bash
cd frontend && npm run lint && npm run build
npx playwright test leases payments tenant-invite --workers=1
```
Expected: all pass.

- [ ] **Step 5: Commit and push**

```bash
git add frontend/src/app/app/leases
git commit -m "Restyle the leases pages onto the app shell"
git push
```
Then report and wait for approval.

---

### Task 7: Maintenance, Messages, Team

**Files:**
- Modify: `frontend/src/app/app/maintenance/page.tsx`, `messages/page.tsx`, `team/page.tsx`

- [ ] **Step 1: Maintenance**

`useShell` + `AppShell`; `<PageHeader title="Maintenance" actions={<Select aria-label="Filter status" …/>} />`
keeping the `aria-label="Filter status"` and every option string. Request rows in `DataList` with a
priority `Badge` (`urgent`/`high` -> danger, `medium` -> warning, `low` -> neutral) and a status
`Badge` (`open` -> brand, `in_progress` -> warning, `resolved` -> success, `cancelled` -> neutral).
The empty state string `No maintenance requests yet.` stays verbatim inside `EmptyState`. Keep the
`aria-label="Status"` and `aria-label="Set priority"` selects. Drop the "Back to dashboard" link.

- [ ] **Step 2: Messages**

Same shell treatment. `PageHeader title="Messages"` with the unread count, category `Select`
(`aria-label="Filter category"`) and a `Mark all read` `Button variant="secondary"`. Rows in
`DataList`: unread rows keep the blue dot (`bg-brand`) and bold title; `Mark read` and `View` become
`Button variant="ghost" size="sm"` and a brand-colored `Link`. `No messages yet.` stays verbatim
inside `EmptyState`. Drop the "Back to dashboard" link.

- [ ] **Step 3: Team**

Same shell treatment. `PageHeader title="Team"`, the invite form in a `Card` with the placeholder
`Email to invite` and the `Invite` button, members and invitations in `DataList`s with a status
`Badge` and a `Revoke` `Button variant="danger" size="sm"`.

- [ ] **Step 4: Verify**

```bash
cd frontend && npm run lint && npm run build
npx playwright test maintenance messages team-invitations --workers=1
```
Expected: all pass.

- [ ] **Step 5: Commit and push**

```bash
git add frontend/src/app/app/maintenance frontend/src/app/app/messages frontend/src/app/app/team
git commit -m "Restyle the maintenance, messages and team pages"
git push
```
Then report and wait for approval.

---

### Task 8: Profile, change-password, tenant portal

**Files:**
- Create: `frontend/src/components/portal-shell.tsx`
- Modify: `frontend/src/app/app/profile/page.tsx`, `change-password/page.tsx`,
  `frontend/src/app/app/page.tsx` (tenant branch)

**Interfaces:**
- Produces: `PortalShell` — same props as `AppShell`, owns its own `<main>`, no sidebar.

- [ ] **Step 1: Create PortalShell**

Create `frontend/src/components/portal-shell.tsx`:

```tsx
"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { linkButton } from "@/components/ui";

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
  return (
    <div className="min-h-screen bg-canvas">
      <header className="border-b border-border bg-surface">
        <div className="mx-auto flex max-w-2xl flex-wrap items-center justify-between gap-3 px-6 py-3">
          <div className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand text-sm font-semibold text-white">
              R
            </span>
            <p data-testid="welcome" className="text-sm text-muted">
              Welcome, {me.name} ({me.role})
            </p>
          </div>
          <nav aria-label="Main" className="flex flex-wrap items-center gap-2">
            <Link href="/app/messages" className={linkButton}>
              Messages{unread > 0 ? ` (${unread})` : ""}
            </Link>
            <Link href="/app/profile" className={linkButton}>
              Contact info
            </Link>
            <Link href="/app/change-password" className={linkButton}>
              Change password
            </Link>
            <button onClick={onLogOut} className={linkButton}>
              Log out
            </button>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-2xl p-6">{children}</main>
    </div>
  );
}
```

- [ ] **Step 2: Convert the tenant dashboard branch**

In `frontend/src/app/app/page.tsx`, wrap the tenant branch in `PortalShell`, delete its
`<p data-testid="welcome">` and its bottom link row (the shell provides both), and put each lease in
a `Card`: address as the card title, rent and dates, landlord contact, the outstanding/overdue pair
as two `StatCard`s, the charges list as a `DataList` with a status `Badge`, and the maintenance
section in its own `Card` — the report form using `Field`/`Input`/`Select`/`Button` and the request
list with priority and status `Badge`s. Keep `aria-label="Priority"`,
`aria-label="Add maintenance image"`, the placeholders `Issue title` and `Description`, and the
buttons `Report`, `Add image`, `Cancel` verbatim. `No lease yet.` goes inside `EmptyState`.

- [ ] **Step 3: Profile and change-password**

Both pages serve tenants and managers, so they pick their shell by role, exactly as the dashboard
does:

```tsx
  const Shell = me.role === "tenant" ? PortalShell : AppShell;
  return (
    <Shell me={me} unread={unread} onLogOut={logOut}>
      …
    </Shell>
  );
```

`profile/page.tsx`: `PageHeader title="Contact info"`, the form in a `Card` with `Field` + `Input`,
keeping the `Edit` / `Save` buttons and the `Phone (optional)` placeholder.
`change-password/page.tsx`: `PageHeader title="Change password"`, form in a `Card`, keeping the
placeholders `Current password`, `New password (min 8 chars)`, `Confirm new password` and the button
`Update password`, plus the mismatch error string the spec asserts.

- [ ] **Step 4: Verify**

```bash
cd frontend && npm run lint && npm run build
npx playwright test profile change-password tenant-invite maintenance --workers=1
```
Expected: all pass.

- [ ] **Step 5: Commit and push**

```bash
git add frontend/src/components/portal-shell.tsx frontend/src/app/app/page.tsx frontend/src/app/app/profile frontend/src/app/app/change-password
git commit -m "Restyle the tenant portal, profile and change-password pages"
git push
```
Then report and wait for approval.

---

### Task 9: Theme toggle, dark-mode pass, full e2e

**Files:**
- Create: `frontend/src/components/ui/theme-toggle.tsx`
- Modify: `frontend/src/app/layout.tsx`, `frontend/src/components/ui/index.ts`,
  `frontend/src/components/app-shell.tsx`, `frontend/src/components/portal-shell.tsx`

- [ ] **Step 1: Add the no-flash script**

In `frontend/src/app/layout.tsx`, inside `<head>`, before `<body>`:

```tsx
        <script
          dangerouslySetInnerHTML={{
            __html: `try{var t=localStorage.getItem("theme");if(t==="dark"||t==="light"){document.documentElement.dataset.theme=t}}catch(e){}`,
          }}
        />
```

This runs before paint, so a dark-mode user never sees a white flash. Without it the page renders
light, then flips once React hydrates.

- [ ] **Step 2: Create ThemeToggle**

Create `frontend/src/components/ui/theme-toggle.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";

type Theme = "light" | "dark" | "system";

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("system");

  useEffect(() => {
    const stored = localStorage.getItem("theme");
    if (stored === "light" || stored === "dark") setTheme(stored);
  }, []);

  function choose(next: Theme) {
    setTheme(next);
    if (next === "system") {
      localStorage.removeItem("theme");
      delete document.documentElement.dataset.theme;
    } else {
      localStorage.setItem("theme", next);
      document.documentElement.dataset.theme = next;
    }
  }

  const next: Theme = theme === "system" ? "light" : theme === "light" ? "dark" : "system";
  const label = theme === "system" ? "System theme" : theme === "light" ? "Light theme" : "Dark theme";

  return (
    <button
      onClick={() => choose(next)}
      className="w-full rounded-lg px-3 py-2 text-left text-sm font-medium text-muted hover:bg-surface-2 hover:text-text"
    >
      {label}
    </button>
  );
}
```

Export it from `frontend/src/components/ui/index.ts` and render it in both shells, below `Log out`.

- [ ] **Step 3: Dark-mode pass**

Run the app and walk every route in dark mode. Look for any surviving hardcoded color — search the
codebase for the leftovers and convert each to a token:

```bash
cd frontend && grep -rn "text-gray-\|bg-gray-\|text-blue-\|bg-blue-\|border-gray-\|text-red-\|text-white" src/app src/components | grep -v "text-white"
```
Every hit outside a `bg-brand`/`bg-danger` pairing is a bug in dark mode: those palette colors do not
flip. Convert to `text-muted`, `text-text`, `bg-surface`, `border-border`, `text-brand` or `text-danger`.

- [ ] **Step 4: Full verification**

```bash
cd frontend && npm run lint && npm run build
npx playwright test --workers=1
cd ../backend && uv run ruff format . && uv run ruff check --fix . && uv run ruff check . && uv run ruff format --check .
```
Expected: all 18 e2e pass; lint, build and ruff clean.

- [ ] **Step 5: Commit, push, confirm CI green**

```bash
git add frontend/src
git commit -m "Add the theme toggle and finish the dark-mode pass"
git push
gh run watch --exit-status
```

Report: the redesign is complete — indigo tokens, a shared component library, a sidebar shell for
managers, a single-column portal for tenants, and dark mode across every page.

---

## Self-Review

**Spec coverage:**
- Tokens with light and dark values, `@theme inline` exposure -> Task 1. ✓
- Arial-over-Geist fix and the "Create Next App" metadata -> Task 1. ✓
- Full component list (Button, Card, StatCard, Field, Input/Select/Textarea, Badge, PageHeader,
  EmptyState, DataList) -> Task 2; `ThemeToggle` -> Task 9. ✓
- `AppShell` with `<nav aria-label="Main">`, the Manage/Settings groups and sole ownership of
  `<main>` -> Task 3. ✓
- `PortalShell` owning its own `<main>` -> Task 8. ✓
- Strict-mode collision on `/app/properties`, resolved by scoping to `getByRole("main")` with no
  user-visible rename -> Task 3, Step 3. ✓
- Recharts `fill="var(--color-brand)"` -> Task 3, Step 2. ✓
- Dark mode: `data-theme` override, guarded media query, no-flash script, toggle -> Tasks 1 and 9. ✓
- Every page in the spec's page-treatment list has a task: marketing/auth -> 4, properties -> 5,
  leases -> 6, maintenance/messages/team -> 7, profile/change-password/tenant -> 8. ✓
- Out of scope (mobile tab bar, vendor directory, search, CSV export, backend changes, new e2e
  specs) -> no task. ✓

**Placeholder scan:** No TBD/TODO. Every new file is given in full. The page tasks specify exact
component substitutions and name-preservation rules rather than reproducing each page's full JSX,
because those conversions are mechanical applications of the Conversion Rules table above and the
pages' logic is explicitly unchanged.

**Type consistency:** `AppShell` and `PortalShell` take the identical prop shape
`{ me: { name, role }, unread: number, onLogOut: () => void, children }`, which is what lets Task 8
select between them with a single `Shell` variable; `useShell()` returns `{ me, unread, logOut }`
matching those props; `Badge` tones (`neutral` / `brand` / `success` / `warning` / `danger`) are the
same five names used in every page task; `linkButton` is a string constant, so it is applied as
`className={linkButton}`, never as a component. ✓
