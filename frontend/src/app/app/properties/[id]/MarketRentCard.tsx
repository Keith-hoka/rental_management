"use client";

import { Card } from "@/components/ui";
import type { MarketRent, MarketRentEnvelope } from "@/lib/marketRent";

export type MarketRentState = "loading" | "ok" | "incomplete" | "unavailable";

const FALLBACK_LABELS: Record<string, string> = {
  bedrooms_all: "all bedrooms",
  dwelling_all: "all dwelling types",
};

function cellLine(market: MarketRent): string {
  const beds = market.bedrooms === null ? "" : `, ${market.bedrooms} bedrooms`;
  const fallback = market.fallback ? ` (${FALLBACK_LABELS[market.fallback] ?? market.fallback})` : "";
  return `${market.dwelling_type}${beds} - ${market.area_label}${fallback}`;
}

function gapLine(currentWeekly: string, gapPct: string): string {
  const gap = Number(gapPct);
  const direction = gap < 0 ? "below" : "above";
  return `Current rent $${currentWeekly}/week, ${Math.abs(gap).toFixed(1)}% ${direction} the market median`;
}

export function MarketRentCard({ state, data }: { state: MarketRentState; data: MarketRentEnvelope | null }) {
  if (state === "loading") {
    return (
      <Card title="Market rent" className="mb-5">
        <p className="text-sm text-muted">Loading market data...</p>
      </Card>
    );
  }
  if (state === "incomplete") {
    return (
      <Card title="Market rent" className="mb-5">
        <p className="text-sm text-muted">
          Add the property&apos;s state and postcode or suburb to see market rent.
        </p>
      </Card>
    );
  }
  if (state === "unavailable" || !data) {
    return (
      <Card title="Market rent" className="mb-5">
        <p className="text-sm text-muted">Market data unavailable</p>
      </Card>
    );
  }
  const market = data.market;
  if (market.estimate_weekly === null || market.band === null) {
    return (
      <Card title="Market rent" className="mb-5">
        <p className="text-sm text-muted">No market data for this area</p>
        <p className="mt-2 text-xs text-muted">{market.disclaimer}</p>
      </Card>
    );
  }
  return (
    <Card title="Market rent" className="mb-5">
      <p className="text-2xl font-semibold text-text" data-testid="market-estimate">
        ${market.estimate_weekly}
        <span className="text-sm font-normal text-muted"> / week</span>
      </p>
      <p className="text-sm text-muted">
        Band ${market.band.low} to ${market.band.high} ({market.basis} of {cellLine(market)})
      </p>
      <p className="mt-2 text-sm text-text">
        {market.period}: n={market.sample_size}
        {market.trend && ` · ${market.trend.change_pct}% vs ${market.trend.from_period}`}
      </p>
      {market.stale && (
        <p className="mt-2 text-sm text-warning">
          Market data runs to {market.period_end}, more than six months before today - treat the
          comparison as indicative.
        </p>
      )}
      {data.current_weekly !== null && data.gap_pct !== null && (
        <p className="mt-2 text-sm text-text" data-testid="market-gap">
          {gapLine(data.current_weekly, data.gap_pct)}
        </p>
      )}
      <p className="mt-3 text-xs text-muted">
        Data: {market.source.name}
        {market.source.licence === "CC BY 4.0" && `, ${market.source.licence}`}
      </p>
      <p className="mt-1 text-xs text-muted">{market.disclaimer}</p>
    </Card>
  );
}
