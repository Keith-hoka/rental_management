"use client";

import { useCallback, useEffect, useState } from "react";
import { Badge, Button, Card } from "@/components/ui";
import {
  getComplianceAudit,
  runComplianceAudit,
  type ComplianceAuditState,
  type ComplianceVerdict,
} from "@/lib/compliance";

const VERDICT_TONE: Record<ComplianceVerdict, "danger" | "success" | "neutral"> = {
  red: "danger",
  green: "success",
  skipped: "neutral",
};

export function ComplianceSection({ leaseId }: { leaseId: string }) {
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

  return (
    <Card
      className="mt-5"
      title="NSW compliance"
      actions={
        <Button onClick={check} disabled={running}>
          {running ? "Checking..." : "Check now"}
        </Button>
      }
    >
      {error && <p className="mb-2 text-sm text-danger-fg">{error}</p>}
      {audit ? (
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone="danger">{counts.red} issues</Badge>
            <Badge tone="success">{counts.green} compliant</Badge>
            <Badge tone="neutral">{counts.skipped} skipped</Badge>
            <span className="text-xs text-muted">as at {audit.as_at}</span>
          </div>
          <ul className="divide-y divide-border">
            {audit.findings.map((f) => (
              <li key={f.rule_id} className="flex items-start gap-2 py-2 text-sm">
                <Badge tone={VERDICT_TONE[f.verdict]}>{f.verdict}</Badge>
                <span className="text-text">
                  {f.summary}
                  {f.citations[0] && (
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
