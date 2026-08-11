import { apiFetch } from "@/lib/api";
import type { JurisdictionStatus } from "@/lib/compliance";

export type ClauseVerdict = "red" | "green" | "yellow" | "skipped";
export type ClauseAuditStatus = "pending" | "running" | "succeeded" | "failed";

export interface ClauseCitation {
  act: string;
  section_no: string;
  label?: string;
  as_at: string;
}

export interface ClauseFinding {
  rule_id: string;
  verdict: ClauseVerdict;
  summary: string;
  clause_quote: string | null;
  citations: ClauseCitation[];
  skip_reason: string | null;
}

export interface ClauseDiscrepancy {
  field: string;
  document_value: string;
  submitted_value: string;
}

export interface ClauseAudit {
  id: string;
  document_id: string;
  document_version_id: string;
  job_id: string;
  status: ClauseAuditStatus;
  findings: ClauseFinding[];
  discrepancies: ClauseDiscrepancy[];
  model: string;
  engine_version: string;
  jurisdiction: string;
  error: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface ClauseAuditListState {
  enabled: boolean;
  audits: ClauseAudit[];
  jurisdiction_status: JurisdictionStatus;
  jurisdiction: string | null;
}

export function listClauseAudits(leaseId: string): Promise<ClauseAuditListState> {
  return apiFetch<ClauseAuditListState>(`/api/v1/leases/${leaseId}/clause-audits`);
}

export function runClauseAudit(leaseId: string, documentId: string): Promise<ClauseAudit> {
  return apiFetch<ClauseAudit>(`/api/v1/leases/${leaseId}/documents/${documentId}/clause-audit`, {
    method: "POST",
  });
}
