"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Badge, Button, Card } from "@/components/ui";
import {
  listClauseAudits,
  runClauseAudit,
  type ClauseAudit,
  type ClauseAuditListState,
  type ClauseFinding,
  type ClauseVerdict,
} from "@/lib/clauseAudit";
import type { DocumentInfo } from "@/lib/documents";

const VERDICT_TONE: Record<ClauseVerdict, "danger" | "success" | "warning" | "neutral"> = {
  red: "danger",
  green: "success",
  yellow: "warning",
  skipped: "neutral",
};

const CLAUSE_RULE_LABELS: Record<string, string> = {
  "nsw.clause.carpet_cleaning": "Prohibited term: professional carpet cleaning (s 19)",
  "nsw.clause.fumigation": "Prohibited term: fumigation at end of tenancy (s 19)",
  "nsw.clause.specified_insurance": "Prohibited term: tenant must take out insurance (s 19)",
  "nsw.clause.landlord_liability_exemption": "Prohibited term: landlord liability exemption (s 19)",
  "nsw.clause.breach_penalty": "Prohibited term: breach penalty or remaining rent (s 19)",
  "nsw.clause.no_breach_rent_inducement": "Prohibited term: conditional rent inducement (s 19)",
  "nsw.clause.specified_contractor": "Prohibited term: specified contractor (s 19)",
  "nsw.clause.specified_contractor_reg":
    "Prohibited term: specified contractor (Reg cl 5, pre-2025)",
  "nsw.clause.utility_provider": "Prohibited term: specific utility provider (Reg cl 5)",
  "nsw.clause.states_rent_payment": "Required term: rent and payment (s 33)",
  "nsw.clause.quiet_enjoyment_term": "Required term: quiet enjoyment (s 50)",
  "nsw.clause.tenant_use_term": "Required term: use of premises (s 51)",
  "nsw.clause.habitability_term": "Required term: clean and habitable (s 52)",
  "nsw.clause.repairs_term": "Required term: repairs (s 63)",
  "nsw.clause.locks_security_term": "Required term: locks and security (s 70)",
  "vic.clause.renter_insurance": "Prohibited term: renter must take out insurance (s 27B)",
  "vic.clause.provider_liability_exemption": "Prohibited term: provider liability exemption (s 27B)",
  "vic.clause.breach_penalty": "Prohibited term: breach penalty or remaining rent (s 27B)",
  "vic.clause.professional_cleaning_required": "Prohibited term: professional cleaning required (s 27B)",
  "vic.clause.professional_cleaning_cost": "Prohibited term: professional cleaning cost (s 27B)",
  "vic.clause.no_breach_rent_inducement": "Prohibited term: conditional rent inducement (s 27B)",
  "vic.clause.preparation_costs": "Prohibited term: agreement preparation costs (s 27B(2))",
  "vic.clause.unreviewed_contract": "Prohibited term: binds renter to unreviewed contract (reg 11)",
  "vic.clause.renter_indemnity": "Prohibited term: renter indemnifies provider (reg 11)",
  "vic.clause.late_availability_claim_waiver": "Prohibited term: bars claim for late availability (reg 11)",
  "vic.clause.costly_payment_method": "Prohibited term: costly payment method (reg 11)",
  "vic.clause.third_party_services": "Prohibited term: nominated third-party services (reg 11)",
  "vic.clause.safety_maintenance_transfer": "Prohibited term: safety maintenance transferred (reg 11)",
  "vic.clause.tribunal_costs_transfer": "Prohibited term: Tribunal costs transferred (reg 11)",
  "vic.clause.insurance_excess_transfer": "Prohibited term: provider's insurance excess transferred (reg 11)",
  "vic.clause.fixed_break_fees": "Prohibited term: fixed break fees without basis (reg 11)",
};

const FIELD_LABELS: Record<string, string> = {
  rent_amount: "Rent",
  rent_frequency: "Rent frequency",
  start_date: "Start date",
  end_date: "End date",
  bond_amount: "Bond",
  rent_in_advance_amount: "Rent in advance",
  holding_deposit_amount: "Holding fee",
  other_security_amount: "Other security",
  break_fee_amount: "Break fee",
};

const VERDICT_ORDER: Record<ClauseVerdict, number> = { red: 0, yellow: 1, green: 2, skipped: 3 };

function label(finding: ClauseFinding): string {
  return CLAUSE_RULE_LABELS[finding.rule_id] ?? finding.rule_id;
}

function skippedDetail(finding: ClauseFinding): string {
  const reason = finding.skip_reason ?? "";
  if (reason.includes("not active")) {
    return "Rule not in force at the audit date.";
  }
  if (reason.startsWith("section")) {
    return `Statutory basis not in force at the audit date (${reason}).`;
  }
  return finding.summary || reason;
}

function StatusChip({ audit }: { audit: ClauseAudit }) {
  if (audit.status === "pending") return <Badge tone="neutral">Queued</Badge>;
  if (audit.status === "running") {
    return (
      <Badge tone="brand">
        <span className="animate-pulse">Running...</span>
      </Badge>
    );
  }
  if (audit.status === "failed") return <Badge tone="danger">Failed</Badge>;
  return (
    <Badge tone="success">
      Completed {audit.completed_at ? new Date(audit.completed_at).toLocaleString() : ""}
    </Badge>
  );
}

function FindingRow({ finding }: { finding: ClauseFinding }) {
  const citation = finding.citations[0];
  if (finding.verdict === "green" || finding.verdict === "skipped") {
    return (
      <li className="flex items-start gap-2 py-2 text-sm">
        <Badge tone={VERDICT_TONE[finding.verdict]}>{finding.verdict}</Badge>
        <span className="text-text">
          <span className="font-medium">{label(finding)}</span>
          {finding.verdict === "skipped" && finding.skip_reason
            ? ` - ${skippedDetail(finding)}`
            : null}
        </span>
      </li>
    );
  }
  return (
    <li className="space-y-1 py-2 text-sm">
      <div className="flex items-start gap-2">
        <Badge tone={VERDICT_TONE[finding.verdict]}>{finding.verdict}</Badge>
        <span className="font-medium text-text">{label(finding)}</span>
      </div>
      <p className="text-muted">{finding.summary}</p>
      {finding.clause_quote ? (
        <blockquote className="border-l-2 border-border pl-2 italic text-muted">
          {finding.clause_quote}
        </blockquote>
      ) : null}
      {citation ? (
        <p className="text-xs text-muted">
          {citation.act}, s {citation.section_no} - as at {citation.as_at}
        </p>
      ) : null}
    </li>
  );
}

function ResultPanel({ audit }: { audit: ClauseAudit }) {
  const ordered = [...audit.findings].sort(
    (a, b) => VERDICT_ORDER[a.verdict] - VERDICT_ORDER[b.verdict],
  );
  return (
    <div className="space-y-2">
      {audit.discrepancies.length > 0 ? (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-muted">
              <th className="py-1 font-medium">Field</th>
              <th className="py-1 font-medium">Document says</th>
              <th className="py-1 font-medium">Form says</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {audit.discrepancies.map((d) => (
              <tr key={d.field}>
                <td className="py-1 font-medium text-text">{FIELD_LABELS[d.field] ?? d.field}</td>
                <td className="py-1 text-text">{d.document_value}</td>
                <td className="py-1 text-text">{d.submitted_value}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
      <ul className="divide-y divide-border">
        {ordered.map((finding) => (
          <FindingRow key={finding.rule_id} finding={finding} />
        ))}
      </ul>
    </div>
  );
}

export function ClauseAuditSection({
  leaseId,
  propertyId,
  documents,
}: {
  leaseId: string;
  propertyId: string;
  documents: DocumentInfo[];
}) {
  const [state, setState] = useState<ClauseAuditListState | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState<Record<string, boolean>>({});
  const leaseDocuments = documents.filter((d) => d.category === "lease");

  // A response for a previous lease must never land in this lease's state.
  const activeLease = useRef(leaseId);
  useEffect(() => {
    activeLease.current = leaseId;
  }, [leaseId]);

  const load = useCallback(() => {
    const requested = leaseId;
    listClauseAudits(requested)
      .then((next) => {
        if (activeLease.current === requested) setState(next);
      })
      .catch(() => {
        if (activeLease.current === requested) setState(null);
      });
  }, [leaseId]);

  useEffect(() => {
    load();
  }, [load]);

  const inFlight = (state?.audits ?? []).some(
    (a) => a.status === "pending" || a.status === "running",
  );

  useEffect(() => {
    if (!inFlight) return;
    const timer = setInterval(() => load(), 10_000);
    return () => clearInterval(timer);
  }, [inFlight, load]);

  if (!state?.enabled || leaseDocuments.length === 0) return null;
  const blocked = state.jurisdiction_status !== "ok";

  const byDocument = new Map<string, ClauseAudit[]>();
  for (const audit of state.audits) {
    const list = byDocument.get(audit.document_id) ?? [];
    list.push(audit);
    byDocument.set(audit.document_id, list);
  }

  async function run(documentId: string) {
    setErrors((prev) => ({ ...prev, [documentId]: "" }));
    setSubmitting((prev) => ({ ...prev, [documentId]: true }));
    try {
      await runClauseAudit(leaseId, documentId);
      load();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Clause audit failed to start";
      setErrors((prev) => ({ ...prev, [documentId]: message }));
    } finally {
      setSubmitting((prev) => ({ ...prev, [documentId]: false }));
    }
  }

  return (
    <Card className="mt-5" title="Clause audit">
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
      <div className="space-y-4">
        {leaseDocuments.map((document) => {
          const audits = byDocument.get(document.id) ?? [];
          const latest = audits[0];
          const latestDone = audits.find((a) => a.status === "succeeded");
          const older = audits.filter((a) => a !== latestDone && a.status === "succeeded");
          const isPdf = document.current_version.content_type === "application/pdf";
          const running = latest?.status === "pending" || latest?.status === "running";
          return (
            <div key={document.id} className="space-y-2 border-b border-border pb-3 last:border-b-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium text-text">{document.title}</span>
                {latest ? <StatusChip audit={latest} /> : null}
                <Button
                  variant="secondary"
                  disabled={!isPdf || running || submitting[document.id] || blocked}
                  onClick={() => void run(document.id)}
                >
                  {submitting[document.id] ? "Submitting..." : "Run clause audit"}
                </Button>
              </div>
              {!isPdf ? (
                <p className="text-xs text-muted">Only PDF documents can be audited.</p>
              ) : null}
              {errors[document.id] ? (
                <p className="text-xs text-danger-fg">{errors[document.id]}</p>
              ) : null}
              {latest?.status === "failed" && latest.error ? (
                <p className="text-xs text-danger-fg">{latest.error}</p>
              ) : null}
              {latestDone ? (
                <>
                  <div className="flex items-center gap-2">
                    <Badge tone="neutral">audited as {latestDone.jurisdiction}</Badge>
                    {(() => {
                      const audited = document.versions.find(
                        (v) => v.id === latestDone.document_version_id,
                      );
                      return audited ? (
                        <span className="text-xs text-muted">
                          Audited version: v{audited.version_number}
                        </span>
                      ) : null;
                    })()}
                  </div>
                  <ResultPanel audit={latestDone} />
                </>
              ) : null}
              {older.length > 0 ? (
                <p className="text-xs text-muted">
                  Previous audits:{" "}
                  {older
                    .map(
                      (a) =>
                        `${new Date(a.created_at).toLocaleDateString()} (` +
                        `${a.findings.filter((f) => f.verdict === "red").length} red, ` +
                        `${a.findings.filter((f) => f.verdict === "yellow").length} yellow)`,
                    )
                    .join("; ")}
                </p>
              ) : null}
            </div>
          );
        })}
      </div>
      <p className="mt-3 text-xs text-muted">General information, not legal advice.</p>
    </Card>
  );
}
