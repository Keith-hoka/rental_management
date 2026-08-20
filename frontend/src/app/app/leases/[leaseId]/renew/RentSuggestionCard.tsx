"use client";

import { Badge, Button, Card } from "@/components/ui";
import type {
  LawCardFinding,
  LawVerdict,
  RentSuggestion,
  SuggestionMarket,
} from "@/lib/rentSuggestion";

const VERDICT_TONE: Record<LawVerdict, "danger" | "success" | "warning" | "neutral"> = {
  red: "danger",
  green: "success",
  yellow: "warning",
  skipped: "neutral",
};

// The subset of ComplianceSection's rule labels relevant to a hypothetical
// rent increase: law_card only ever carries rent_increase / fixed_term_increase rules.
const RULE_LABELS: Record<string, string> = {
  "nsw.rent_increase_frequency": "Rent increase frequency (s41)",
  "nsw.rent_increase_first_year": "First-year rent increase (s41)",
  "nsw.rent_increase_notice": "Rent increase notice (s41)",
  "nsw.fixed_term_increase_disclosure": "Fixed-term increase disclosure (s42)",
  "vic.rent_increase_frequency": "Rent increase frequency (s 44)",
  "vic.fixed_term_increase_provision": "Fixed-term increase provision (s 44)",
};

const FALLBACK_LABELS: Record<string, string> = {
  bedrooms_all: "all bedrooms",
  dwelling_all: "all dwelling types",
};

function marketLine(market: SuggestionMarket): string {
  const base = `Market ${market.period}: median ${market.median}, n=${market.sample_size}`;
  if (!market.fallback) return base;
  return `${base} (${FALLBACK_LABELS[market.fallback] ?? market.fallback})`;
}

function LawCardRow({ finding }: { finding: LawCardFinding }) {
  const citation = finding.citations[0];
  return (
    <li className="flex items-start gap-2 py-2 text-sm">
      <Badge tone={VERDICT_TONE[finding.verdict]}>{finding.verdict}</Badge>
      <span className="text-text">
        <span className="font-medium">{RULE_LABELS[finding.rule_id] ?? finding.rule_id}</span>
        {" - "}
        {finding.summary}
        {citation && (
          <span className="text-muted"> ({citation.label ?? `s ${citation.section_no}`})</span>
        )}
      </span>
    </li>
  );
}

export function RentSuggestionCard({
  suggestion,
  onUse,
}: {
  suggestion: RentSuggestion;
  onUse: (weekly: number) => void;
}) {
  const { market } = suggestion;
  // CC BY 4.0 is currently only VIC's licence; checking the licence itself
  // (rather than guessing at the jurisdiction, which this response doesn't carry)
  // keeps the attribution tied to the data it actually covers.
  const requiresCcByAttribution = market?.source.licence === "CC BY 4.0";

  return (
    <Card className="mt-3" title="Suggested rent">
      <div className="flex items-baseline gap-2">
        <span className="text-2xl font-semibold text-text">
          ${suggestion.suggested_weekly}
        </span>
        <span className="text-sm text-muted">/ week</span>
      </div>
      <p className="text-sm text-muted">
        Current ${suggestion.current_weekly} / week - range ${suggestion.range.low} to $
        {suggestion.range.high}
      </p>
      {market && <p className="mt-2 text-sm text-text">{marketLine(market)}</p>}
      {market && <p className="text-xs text-muted">Source: {market.source.name}</p>}
      {requiresCcByAttribution && (
        <p className="text-xs text-muted">Data: Homes Victoria Rental Report, CC BY 4.0</p>
      )}
      {suggestion.law_card.length > 0 && (
        <ul className="mt-2 divide-y divide-border">
          {suggestion.law_card.map((finding) => (
            <LawCardRow key={finding.rule_id} finding={finding} />
          ))}
        </ul>
      )}
      <p className="mt-2 text-sm text-text">{suggestion.reasoning}</p>
      <p className="mt-1 text-xs text-muted">{suggestion.disclaimer}</p>
      <Button
        type="button"
        variant="secondary"
        className="mt-3"
        onClick={() => onUse(Number(suggestion.suggested_weekly))}
      >
        Use suggestion
      </Button>
    </Card>
  );
}
