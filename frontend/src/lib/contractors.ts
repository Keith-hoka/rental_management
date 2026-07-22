import { apiFetch } from "@/lib/api";

export interface ContractorInfo {
  id: string;
  name: string;
  trade: string | null;
  phone: string | null;
  email: string | null;
  created_at: string;
}

export interface ContractorInput {
  name: string;
  trade?: string | null;
  phone?: string | null;
  email?: string | null;
}

export function listContractors() {
  return apiFetch<ContractorInfo[]>("/api/v1/contractors");
}

export function createContractor(input: ContractorInput) {
  return apiFetch<ContractorInfo>("/api/v1/contractors", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function updateContractor(id: string, input: Partial<ContractorInput>) {
  return apiFetch<ContractorInfo>(`/api/v1/contractors/${id}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export function deleteContractor(id: string) {
  return apiFetch<void>(`/api/v1/contractors/${id}`, { method: "DELETE" });
}
