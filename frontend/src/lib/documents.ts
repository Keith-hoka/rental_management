import { apiFetch, API_BASE_URL } from "@/lib/api";
import { getAccessToken } from "@/lib/auth";

export type DocumentCategory = "lease" | "report" | "receipt" | "other";

export interface DocumentVersionInfo {
  id: string;
  version_number: number;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  created_at: string;
}

export interface DocumentInfo {
  id: string;
  title: string;
  category: DocumentCategory;
  version_count: number;
  current_version: DocumentVersionInfo;
  versions: DocumentVersionInfo[];
  created_at: string;
}

export function listLeaseDocuments(leaseId: string) {
  return apiFetch<DocumentInfo[]>(`/api/v1/leases/${leaseId}/documents`);
}

export function listMyLeaseDocuments(leaseId: string) {
  return apiFetch<DocumentInfo[]>(`/api/v1/me/leases/${leaseId}/documents`);
}

export function deleteDocument(documentId: string) {
  return apiFetch<void>(`/api/v1/documents/${documentId}`, { method: "DELETE" });
}

async function uploadFile(url: string, form: FormData): Promise<DocumentInfo> {
  const token = getAccessToken();
  const response = await fetch(`${API_BASE_URL}${url}`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  });
  if (!response.ok) throw new Error("Upload failed");
  return response.json();
}

export function uploadDocument(
  leaseId: string,
  title: string,
  category: DocumentCategory,
  file: File,
) {
  const form = new FormData();
  form.append("title", title);
  form.append("category", category);
  form.append("file", file);
  return uploadFile(`/api/v1/leases/${leaseId}/documents`, form);
}

export function uploadVersion(documentId: string, file: File) {
  const form = new FormData();
  form.append("file", file);
  return uploadFile(`/api/v1/documents/${documentId}/versions`, form);
}

export async function fetchDocumentBlob(versionId: string): Promise<Blob> {
  const token = getAccessToken();
  const response = await fetch(
    `${API_BASE_URL}/api/v1/documents/versions/${versionId}/download`,
    { cache: "no-store", headers: token ? { Authorization: `Bearer ${token}` } : {} },
  );
  if (!response.ok) throw new Error("Download failed");
  return response.blob();
}
