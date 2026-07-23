"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { search, type SearchHit, type SearchResults } from "@/lib/search";
import { AppShell } from "@/components/app-shell";
import { useShell } from "@/components/use-shell";
import { Card, EmptyState, Input, PageHeader } from "@/components/ui";

const GROUPS: { key: keyof SearchResults; label: string }[] = [
  { key: "properties", label: "Properties" },
  { key: "leases", label: "Leases" },
  { key: "maintenance", label: "Maintenance" },
  { key: "documents", label: "Documents" },
];

const EMPTY: SearchResults = { properties: [], leases: [], maintenance: [], documents: [] };

function HitList({ hits }: { hits: SearchHit[] }) {
  return (
    <ul className="space-y-1">
      {hits.map((h, i) => (
        <li key={i}>
          <Link href={h.link} className="block rounded-lg p-2 hover:bg-surface-2">
            <span className="font-medium text-text">{h.title}</span>
            {h.subtitle && <span className="ml-2 text-sm text-muted">{h.subtitle}</span>}
          </Link>
        </li>
      ))}
    </ul>
  );
}

/** Keyed by the current query, so a new query remounts it with the new initial. */
function SearchBox({ initial, onSearch }: { initial: string; onSearch: (v: string) => void }) {
  const [term, setTerm] = useState(initial);
  return (
    <form
      className="mb-5"
      onSubmit={(e) => {
        e.preventDefault();
        const value = term.trim();
        if (value) onSearch(value);
      }}
    >
      <Input
        type="search"
        aria-label="Search term"
        placeholder="Search properties, tenants, maintenance, documents"
        value={term}
        onChange={(e) => setTerm(e.target.value)}
      />
    </form>
  );
}

function SearchResultsView() {
  const { me, unread, logOut } = useShell();
  const router = useRouter();
  const q = useSearchParams().get("q") ?? "";
  // Results are tagged with their query; a stale fetch for an old query is
  // simply not rendered, so no state reset is needed when q changes.
  const [fetched, setFetched] = useState<{ q: string; data: SearchResults } | null>(null);

  useEffect(() => {
    if (!me || !q) return;
    let active = true;
    search(q)
      .then((data) => active && setFetched({ q, data }))
      .catch(() => active && setFetched({ q, data: EMPTY }));
    return () => {
      active = false;
    };
  }, [me, q]);

  if (!me) return null;

  const results = fetched && fetched.q === q ? fetched.data : null;
  const total = results ? GROUPS.reduce((n, g) => n + results[g.key].length, 0) : 0;

  return (
    <AppShell me={me} unread={unread} onLogOut={logOut}>
      <PageHeader title="Search" />
      <SearchBox
        key={q}
        initial={q}
        onSearch={(value) => router.push(`/app/search?q=${encodeURIComponent(value)}`)}
      />
      {!q ? (
        <EmptyState>Type a search term above.</EmptyState>
      ) : results === null || total === 0 ? (
        <EmptyState>No results.</EmptyState>
      ) : (
        <div className="space-y-5">
          {GROUPS.filter((g) => results[g.key].length > 0).map((g) => (
            <Card key={g.key} title={g.label}>
              <HitList hits={results[g.key]} />
            </Card>
          ))}
        </div>
      )}
    </AppShell>
  );
}

export default function SearchPage() {
  return (
    <Suspense>
      <SearchResultsView />
    </Suspense>
  );
}
