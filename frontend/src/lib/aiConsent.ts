import { apiFetch } from "@/lib/api";

export type AiConsentState = {
  features: Record<string, boolean>;
  disclosure_version: string;
};

export function getAiConsents(): Promise<AiConsentState> {
  return apiFetch<AiConsentState>("/api/ai-consents");
}

export function setAiConsent(feature: string, enabled: boolean): Promise<AiConsentState> {
  return apiFetch<AiConsentState>(`/api/ai-consents/${feature}`, {
    method: "POST",
    body: JSON.stringify({ enabled }),
  });
}
