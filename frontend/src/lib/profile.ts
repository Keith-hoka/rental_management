import { apiFetch } from "@/lib/api";

export interface Me {
  id: string;
  email: string;
  name: string;
  phone: string | null;
  role: string;
  organization_id: string;
}

export function getMe() {
  return apiFetch<Me>("/api/v1/auth/me");
}

export function updateProfile(body: { name: string; phone: string }) {
  return apiFetch<Me>("/api/v1/auth/me", {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}
