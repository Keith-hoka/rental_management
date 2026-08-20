"use client";

import { useEffect, useState } from "react";
import { ApiError } from "@/lib/api";
import { getAiConsents, setAiConsent, type AiConsentState } from "@/lib/aiConsent";
import { AiDisclosure } from "@/content/aiDisclosure";
import { AppShell } from "@/components/app-shell";
import { PortalShell } from "@/components/portal-shell";
import { useShell } from "@/components/use-shell";
import { Card, PageHeader } from "@/components/ui";

const FEATURES: { key: string; label: string; description?: string }[] = [
  { key: "clause_audit", label: "Clause audit" },
  {
    key: "rent_ai",
    label: "Rent AI",
    description: "Suggests a renewal rent using recent rental market data and the property's rent-increase rules.",
  },
];

function FeatureSwitch({
  id,
  label,
  description,
  checked,
  disabled,
  onToggle,
}: {
  id: string;
  label: string;
  description?: string;
  checked: boolean;
  disabled: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="flex items-center justify-between border-b border-border py-3 last:border-b-0">
      <div>
        <span id={id} className="text-sm font-medium text-text">
          {label}
        </span>
        {description && <p className="mt-0.5 text-xs text-muted">{description}</p>}
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-labelledby={id}
        disabled={disabled}
        onClick={onToggle}
        className={`relative h-6 w-11 shrink-0 rounded-full transition-colors disabled:opacity-50 ${
          checked ? "bg-brand" : "border border-strong bg-surface-2"
        }`}
      >
        <span
          className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform ${
            checked ? "translate-x-5" : "translate-x-0.5"
          }`}
        />
      </button>
    </div>
  );
}

export default function AiSettingsPage() {
  const { me: user, unread, logOut } = useShell();
  // Its own fetch: useShell only carries the name and role the chrome needs.
  const [consent, setConsent] = useState<AiConsentState | null>(null);
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    let active = true;
    getAiConsents()
      .then((state) => active && setConsent(state))
      .catch(() => active && setError("Could not load AI settings"));
    return () => {
      active = false;
    };
  }, [user]);

  if (!user) return null;

  const Shell = user.role === "tenant" ? PortalShell : AppShell;
  const isLandlord = user.role === "landlord";

  async function toggle(feature: string, next: boolean) {
    setError(null);
    setPending(feature);
    try {
      setConsent(await setAiConsent(feature, next));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not update AI settings");
    } finally {
      setPending(null);
    }
  }

  return (
    <Shell me={user} unread={unread} onLogOut={logOut}>
      <div className="mx-auto max-w-lg">
        <PageHeader title="AI settings" />
        {error && (
          <p className="mb-3 text-sm text-danger" role="alert">
            {error}
          </p>
        )}

        <Card>
          <AiDisclosure />
          {consent && (
            <p className="mt-3 text-xs text-muted">
              Disclosure version: {consent.disclosure_version}
            </p>
          )}
        </Card>

        <Card className="mt-5" title="Features">
          {!isLandlord && (
            <p className="mb-3 text-sm text-muted">
              Only a landlord can change these settings.
            </p>
          )}
          {FEATURES.map((feature) => (
            <FeatureSwitch
              key={feature.key}
              id={`ai-feature-${feature.key}`}
              label={feature.label}
              description={feature.description}
              checked={consent?.features[feature.key] ?? false}
              disabled={!isLandlord || consent === null || pending === feature.key}
              onToggle={() =>
                void toggle(feature.key, !(consent?.features[feature.key] ?? false))
              }
            />
          ))}
        </Card>
      </div>
    </Shell>
  );
}
