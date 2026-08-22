import { apiFetch } from "@/lib/api";
import type { SuggestionSource } from "@/lib/rentSuggestion";

export interface MarketSeriesPoint {
  period: string;
  median: string;
  p25: string | null;
  p75: string | null;
  sample_size: number;
}

export interface MarketTrend {
  from_period: string;
  from_median: string;
  change_pct: string;
}

export interface MarketRent {
  jurisdiction: "NSW" | "VIC";
  area: string;
  area_label: string | null;
  dwelling_type: string;
  bedrooms: number | null;
  estimate_weekly: string | null;
  band: { low: string; high: string } | null;
  basis: "median";
  period: string | null;
  period_end: string | null;
  stale: boolean;
  sample_size: number | null;
  fallback: string | null;
  series: MarketSeriesPoint[];
  trend: MarketTrend | null;
  source: SuggestionSource;
  disclaimer: string;
}

export interface MarketRentEnvelope {
  market: MarketRent;
  current_weekly: string | null;
  gap_pct: string | null;
}

export function getMarketRent(propertyId: string): Promise<MarketRentEnvelope> {
  return apiFetch<MarketRentEnvelope>(`/api/v1/properties/${propertyId}/market-rent`);
}
