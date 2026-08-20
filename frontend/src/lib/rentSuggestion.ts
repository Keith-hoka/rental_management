import { apiFetch } from "@/lib/api";

export type LawVerdict = "red" | "green" | "yellow" | "skipped";
export type MarketGap = "within" | "above_cap" | "below_current" | "no_data";

export interface SuggestionCitation {
  act: string;
  section_no: string;
  as_at: string;
  label?: string | null;
}

export interface LawCardFinding {
  rule_id: string;
  verdict: LawVerdict;
  summary: string;
  citations: SuggestionCitation[];
  skip_reason: string | null;
}

export interface SuggestionSource {
  name: string;
  url: string;
  licence: string;
}

export interface SuggestionMarket {
  period: string;
  median: string;
  p25: string | null;
  p75: string | null;
  sample_size: number;
  fallback: string | null;
  source: SuggestionSource;
}

export interface SuggestionRange {
  low: string;
  high: string;
}

export interface RentSuggestion {
  current_weekly: string;
  suggested_weekly: string;
  range: SuggestionRange;
  market_gap: MarketGap;
  market: SuggestionMarket | null;
  law_card: LawCardFinding[];
  law_blocked: boolean;
  reasoning: string;
  model: string | null;
  engine_version: string;
  disclaimer: string;
}

export function getRentSuggestion(
  leaseId: string,
  renewalStart: string,
): Promise<RentSuggestion> {
  return apiFetch<RentSuggestion>(`/api/v1/leases/${leaseId}/rent-suggestion`, {
    method: "POST",
    body: JSON.stringify({ renewal_start: renewalStart }),
  });
}
