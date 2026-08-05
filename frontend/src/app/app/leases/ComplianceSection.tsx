"use client";

import { useCallback, useEffect, useState } from "react";
import { Badge, Button, Card } from "@/components/ui";
import {
  getComplianceAudit,
  runComplianceAudit,
  type ComplianceAuditState,
  type ComplianceFinding,
  type ComplianceVerdict,
} from "@/lib/compliance";

const VERDICT_TONE: Record<ComplianceVerdict, "danger" | "success" | "neutral"> = {
  red: "danger",
  green: "success",
  skipped: "neutral",
};

const RULE_LABELS: Record<string, string> = {
  "nsw.bond_max_4_weeks": "Bond cap (s159)",
  "nsw.rent_in_advance_max": "Rent in advance cap (s33)",
  "nsw.holding_fee_max_1_week": "Holding fee cap (s24)",
  "nsw.rent_increase_frequency": "Rent increase frequency (s41)",
  "nsw.rent_increase_first_year": "First-year rent increase (s41)",
  "nsw.rent_increase_notice": "Rent increase notice (s41)",
  "nsw.fixed_term_increase_disclosure": "Fixed-term increase disclosure (s42)",
  "nsw.no_other_security": "No security besides bond (s160)",
  "nsw.break_fee_cap": "Break fee cap (s107)",
  "vic.bond_max_1_month": "Bond cap (s 31)",
  "vic.advance_max_1_month": "Rent in advance cap (s 40)",
  "vic.rent_increase_frequency": "Rent increase frequency (s 44)",
  "vic.fixed_term_increase_provision": "Fixed-term increase provision (s 44)",
};

const NOT_FILLED = "not filled in for this lease";

const FIELD_HINTS: Record<string, string> = {
  bond_amount: "the bond amount",
  rent_in_advance_amount: `the advance rent amount (${NOT_FILLED})`,
  holding_deposit_amount: `the holding fee amount (${NOT_FILLED})`,
  other_security_amount: `the other-security amount (${NOT_FILLED})`,
  break_fee_amount: `the break fee amount (${NOT_FILLED})`,
  rent_increases: "a rent increase history, which builds from renewals with a higher rent",
  end_date: "the end date",
};

function skippedDetail(finding: ComplianceFinding): string {
  const reason = finding.skip_reason ?? "";
  if (reason.startsWith("missing input:")) {
    const fields = reason
      .slice("missing input:".length)
      .split(",")
      .map((name) => name.trim());
    const hints = fields.map((name) => FIELD_HINTS[name] ?? name);
    return `Needs ${hints.join(" and ")}.`;
  }
  if (finding.rule_id === "nsw.fixed_term_increase_disclosure" && reason.includes("not active")) {
    return "No longer applies: s42 was repealed on 13 Dec 2024.";
  }
  if (reason.includes("not active")) {
    return "Rule not in force at the audit date.";
  }
  if (reason.startsWith("section")) {
    return `Statutory basis not in force at the audit date (${reason}).`;
  }
  return finding.summary;
}

export function ComplianceSection({
  leaseId,
  propertyId,
}: {
  leaseId: string;
  propertyId: string;
}) {
  const [state, setState] = useState<ComplianceAuditState | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    getComplianceAudit(leaseId)
      .then(setState)
      .catch(() => setState(null));
  }, [leaseId]);

  useEffect(() => {
    load();
  }, [load]);

  if (!state?.enabled) return null;
  const audit = state.audit;
  const counts: Record<ComplianceVerdict, number> = { red: 0, green: 0, skipped: 0 };
  audit?.findings.forEach((f) => {
    counts[f.verdict] += 1;
  });

  async function check() {
    setRunning(true);
    setError(null);
    try {
      await runComplianceAudit(leaseId);
      load();
    } catch {
      setError("Compliance check failed. Try again later.");
    } finally {
      setRunning(false);
    }
  }

  const title = state.jurisdiction ? `${state.jurisdiction} compliance` : "Compliance";
  const blocked = state.jurisdiction_status !== "ok";
  return (
    <Card
      className="mt-5"
      title={title}
      actions={
        <Button onClick={check} disabled={running || blocked}>
          {running ? "Checking..." : "Check now"}
        </Button>
      }
    >
      {blocked && (
        <p className="mb-2 text-sm text-muted">
          {state.jurisdiction_status === "missing" ? (
            <>
              Set the property&apos;s state to enable compliance checks.{" "}
              <a className="underline" href={`/app/properties/${propertyId}/edit`}>
                Edit property
              </a>
            </>
          ) : (
            "Compliance checks are not yet supported for this property's state."
          )}
        </p>
      )}
      {error && <p className="mb-2 text-sm text-danger-fg">{error}</p>}
      {audit ? (
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone="danger">{counts.red} issues</Badge>
            <Badge tone="success">{counts.green} compliant</Badge>
            <Badge tone="neutral">{counts.skipped} skipped</Badge>
            <Badge tone="neutral">audited as {audit.jurisdiction}</Badge>
            <span className="text-xs text-muted">as at {audit.as_at}</span>
          </div>
          <ul className="divide-y divide-border">
            {audit.findings.map((f) => (
              <li key={f.rule_id} className="flex items-start gap-2 py-2 text-sm">
                <Badge tone={VERDICT_TONE[f.verdict]}>{f.verdict}</Badge>
                <span className="text-text">
                  <span className="font-medium">{RULE_LABELS[f.rule_id] ?? f.rule_id}</span>
                  {" - "}
                  {f.verdict === "skipped" ? skippedDetail(f) : f.summary}
                  {!RULE_LABELS[f.rule_id] && f.citations[0] && (
                    <span className="text-muted"> (s{f.citations[0].section_no})</span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="text-sm text-muted">No compliance check has run yet.</p>
      )}
      <p className="mt-3 text-xs text-muted">General information, not legal advice.</p>
    </Card>
  );
}
