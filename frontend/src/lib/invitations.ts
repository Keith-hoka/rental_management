import { apiFetch } from "@/lib/api";

export interface Invitation {
  id: string;
  email: string;
  role: "property_manager";
  status: "pending" | "accepted" | "revoked";
  expires_at: string;
}

export function listInvitations() {
  return apiFetch<Invitation[]>("/api/v1/invitations");
}

export function createInvitation(email: string) {
  return apiFetch<Invitation>("/api/v1/invitations", {
    method: "POST",
    body: JSON.stringify({ email, role: "property_manager" }),
  });
}

export function revokeInvitation(id: string) {
  return apiFetch<void>(`/api/v1/invitations/${id}`, { method: "DELETE" });
}
