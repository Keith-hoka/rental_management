import { apiFetch } from "@/lib/api";

export interface SearchHit {
  title: string;
  subtitle: string | null;
  link: string;
}

export interface SearchResults {
  properties: SearchHit[];
  leases: SearchHit[];
  maintenance: SearchHit[];
  documents: SearchHit[];
}

export function search(q: string) {
  return apiFetch<SearchResults>(`/api/v1/search?q=${encodeURIComponent(q)}`);
}
