import { apiFetch } from "@/lib/api";

export type ComplianceVerdict = "red" | "green" | "skipped";

export interface ComplianceCitation {
  act: string;
  section_no: string;
}

export interface ComplianceFinding {
  rule_id: string;
  verdict: ComplianceVerdict;
  summary: string;
  citations: ComplianceCitation[];
  skip_reason: string | null;
}

export interface ComplianceAudit {
  id: string;
  audit_id: string;
  as_at: string;
  findings: ComplianceFinding[];
  jurisdiction: string;
  created_at: string;
}

export type JurisdictionStatus = "ok" | "missing" | "unsupported";

export interface ComplianceAuditState {
  enabled: boolean;
  audit: ComplianceAudit | null;
  jurisdiction_status: JurisdictionStatus;
  jurisdiction: string | null;
}

export function getComplianceAudit(leaseId: string): Promise<ComplianceAuditState> {
  return apiFetch<ComplianceAuditState>(`/api/v1/leases/${leaseId}/compliance-audit`);
}

export function runComplianceAudit(leaseId: string): Promise<ComplianceAudit> {
  return apiFetch<ComplianceAudit>(`/api/v1/leases/${leaseId}/compliance-audit`, {
    method: "POST",
  });
}
