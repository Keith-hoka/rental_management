import Link from "next/link";
import { ThemeToggle } from "@/components/ui";

const POINTS = [
  { title: "Rent collection", body: "Charges generate themselves and payments settle oldest first." },
  { title: "Maintenance tracking", body: "Tenants report issues with photos; you set priority and status." },
  { title: "Communication tools", body: "Expiry, rent and maintenance updates reach everyone by email and inbox." },
];

export default function Home() {
  return (
    <main className="relative flex min-h-screen items-center justify-center bg-canvas p-6">
      <div className="absolute top-6 right-6">
        <ThemeToggle />
      </div>
      <div className="w-full max-w-2xl">
        <div className="mb-6 flex items-center justify-center gap-2">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand font-semibold text-white">
            R
          </span>
          <span className="text-xl font-semibold text-text">Rentals</span>
        </div>

        <div className="rounded-xl border border-border bg-surface p-8 text-center shadow-[var(--shadow-card)]">
          <h1 className="text-3xl font-semibold text-text">Simplify property management in one app</h1>
          <p className="mx-auto mt-3 max-w-md text-muted">
            Rent collection, maintenance tracking and communication tools for landlords, property
            managers and their tenants.
          </p>

          <div className="mt-7 flex flex-wrap items-center justify-center gap-3">
            <Link
              href="/login"
              className="rounded-lg bg-brand px-5 py-2.5 text-sm font-medium text-white hover:bg-brand-hover"
            >
              Get started
            </Link>
            <Link
              href="/signup"
              className="rounded-lg border border-strong px-5 py-2.5 text-sm font-medium text-text hover:bg-surface-2"
            >
              Create an account
            </Link>
          </div>

          <dl className="mt-8 grid gap-4 border-t border-border pt-6 text-left sm:grid-cols-3">
            {POINTS.map((point) => (
              <div key={point.title}>
                <dt className="text-sm font-medium text-text">{point.title}</dt>
                <dd className="mt-1 text-sm text-muted">{point.body}</dd>
              </div>
            ))}
          </dl>
        </div>
      </div>
    </main>
  );
}
