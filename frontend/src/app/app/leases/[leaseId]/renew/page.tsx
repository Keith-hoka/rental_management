"use client";

import { use, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ApiError } from "@/lib/api";
import { getLease, renewLease, type Lease, type LeaseFrequency } from "@/lib/leases";
import { getRentSuggestion, type RentSuggestion } from "@/lib/rentSuggestion";
import { AppShell } from "@/components/app-shell";
import { useShell } from "@/components/use-shell";
import { Button, Card, Field, Input, PageHeader, Select } from "@/components/ui";
import { RentSuggestionCard } from "./RentSuggestionCard";

/** The day after an ISO date. The overlap check is inclusive, so a renewal
 * cannot start on the day the old lease ends. */
function dayAfter(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + 1);
  return d.toISOString().slice(0, 10);
}

/** A weekly rent expressed in the lease's own payment frequency, rounded to
 * whole dollars - the inverse of the compliance service's own conversion. */
function toFrequencyAmount(weekly: number, frequency: LeaseFrequency): number {
  if (frequency === "fortnightly") return Math.round((weekly * 52) / 26);
  if (frequency === "monthly") return Math.round((weekly * 52) / 12);
  return Math.round(weekly);
}

function AiConsentPrompt() {
  return (
    <div data-testid="ai-consent-card" className="space-y-1 text-sm text-muted">
      <p>AI features are disabled. A landlord can enable them in Settings.</p>
      <Link className="underline" href="/app/settings/ai">
        Open AI settings
      </Link>
    </div>
  );
}

export default function RenewLeasePage({ params }: { params: Promise<{ leaseId: string }> }) {
  const { leaseId } = use(params);
  const router = useRouter();
  const { me, unread, logOut } = useShell();
  const [lease, setLease] = useState<Lease | null>(null);
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [rent, setRent] = useState(0);
  const [frequency, setFrequency] = useState<LeaseFrequency>("monthly");
  const [bond, setBond] = useState<number | null>(null);
  const [advance, setAdvance] = useState<number | null>(null);
  const [holdingFee, setHoldingFee] = useState<number | null>(null);
  const [otherSecurity, setOtherSecurity] = useState<number | null>(null);
  const [breakFee, setBreakFee] = useState<number | null>(null);
  const [noticeDays, setNoticeDays] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [suggestion, setSuggestion] = useState<RentSuggestion | null>(null);
  const [suggesting, setSuggesting] = useState(false);
  const [suggestionError, setSuggestionError] = useState<string | null>(null);
  const [consentBlocked, setConsentBlocked] = useState(false);

  useEffect(() => {
    if (!me) return;
    let active = true;
    getLease(leaseId)
      .then((l) => {
        if (!active) return;
        setLease(l);
        setStartDate(dayAfter(l.end_date));
        setRent(l.rent_amount);
        setFrequency(l.rent_frequency);
        setBond(l.bond_amount);
        setAdvance(l.rent_in_advance_amount);
        setHoldingFee(l.holding_deposit_amount);
        setOtherSecurity(l.other_security_amount);
        setBreakFee(l.break_fee_amount);
        setNoticeDays(l.notice_period_days);
      })
      .catch(() => active && setError("Lease not found"));
    return () => {
      active = false;
    };
  }, [leaseId, me]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const renewal = await renewLease(leaseId, {
        start_date: startDate,
        end_date: endDate,
        rent_amount: rent,
        rent_frequency: frequency,
        bond_amount: bond,
        rent_in_advance_amount: advance,
        holding_deposit_amount: holdingFee,
        other_security_amount: otherSecurity,
        break_fee_amount: breakFee,
        notice_period_days: noticeDays,
      });
      router.push(`/app/leases/${renewal.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Renewal failed");
    }
  }

  async function suggestRent() {
    setSuggestionError(null);
    setConsentBlocked(false);
    setSuggesting(true);
    try {
      setSuggestion(await getRentSuggestion(leaseId, startDate));
    } catch (err) {
      const detail = err instanceof ApiError ? (err.detail as { code?: string } | null) : null;
      if (detail?.code === "ai_consent_required") {
        setConsentBlocked(true);
      } else if (detail?.code === "judge_timeout") {
        setSuggestionError("Suggestion timed out, try again.");
      } else {
        setSuggestionError("Suggestion unavailable, try again.");
      }
    } finally {
      setSuggesting(false);
    }
  }

  function useSuggestedRent(weekly: number) {
    setRent(toFrequencyAmount(weekly, frequency));
  }

  /** A renewal-start edit invalidates any suggestion computed for the old
   * date: the law card is date-driven, so a stale card could show a
   * suggestion the new date would actually block. */
  function updateStartDate(value: string) {
    setStartDate(value);
    setSuggestion(null);
    setSuggestionError(null);
  }

  if (!me) return null;
  if (!lease)
    return (
      <AppShell me={me} unread={unread} onLogOut={logOut}>
        {error && <p className="text-danger">{error}</p>}
      </AppShell>
    );

  return (
    <AppShell me={me} unread={unread} onLogOut={logOut}>
      <div className="mx-auto max-w-2xl">
        <PageHeader title="Renew lease" />
        <p className="mb-4 text-sm text-muted">
          The same tenants carry over. To let someone else move in, add a new lease instead.
        </p>
        {error && (
          <p className="mb-3 text-sm text-danger" role="alert">
            {error}
          </p>
        )}
      </div>
      <Card className="mx-auto max-w-2xl">
        <div className="mb-4 rounded-lg border border-border p-3 text-sm">
          <p className="font-medium text-text">{lease.tenant_name}</p>
          <p className="text-muted">{lease.tenant_email}</p>
          {lease.co_tenants.map((c) => (
            <p key={c.email} className="text-muted">
              {c.name} ({c.email})
            </p>
          ))}
        </div>
        <form onSubmit={onSubmit} className="space-y-3">
          <div className="flex gap-2">
            <div className="flex-1">
              <Field label="Rent">
                <Input
                  type="number"
                  min={0}
                  required
                  value={rent || ""}
                  onChange={(e) => setRent(Number(e.target.value))}
                />
              </Field>
            </div>
            {/* A plain sibling, not nested in the Rent Field: Field wraps its
                contents in one <label>, and a second interactive control
                inside it breaks the implicit "Rent" label association. */}
            <div className="self-end">
              <Button
                type="button"
                variant="secondary"
                disabled={!startDate || suggesting}
                onClick={() => void suggestRent()}
              >
                {suggesting ? "Suggesting..." : "Suggest rent"}
              </Button>
            </div>
            <div className="flex-1">
              <Field label="Frequency">
                <Select
                  value={frequency}
                  onChange={(e) => setFrequency(e.target.value as LeaseFrequency)}
                >
                  <option value="weekly">Weekly</option>
                  <option value="fortnightly">Fortnightly</option>
                  <option value="monthly">Monthly</option>
                </Select>
              </Field>
            </div>
          </div>
          {consentBlocked && <AiConsentPrompt />}
          {suggestionError && (
            <p className="text-sm text-danger" role="alert">
              {suggestionError}
            </p>
          )}
          {suggestion && <RentSuggestionCard suggestion={suggestion} onUse={useSuggestedRent} />}
          <div className="flex gap-2">
            <div className="flex-1">
              <Field label="Bond (optional)">
                <Input
                  type="number"
                  min={0}
                  value={bond ?? ""}
                  onChange={(e) => setBond(e.target.value === "" ? null : Number(e.target.value))}
                />
              </Field>
            </div>
            <div className="flex-1">
              <Field label="Notice period (days)">
                <Input
                  type="number"
                  min={0}
                  value={noticeDays ?? ""}
                  onChange={(e) =>
                    setNoticeDays(e.target.value === "" ? null : Number(e.target.value))
                  }
                />
              </Field>
            </div>
          </div>
          <p className="text-sm font-medium text-text">Upfront money &amp; fees (optional)</p>
          <div className="grid grid-cols-2 gap-2">
            {(
              [
                ["Rent in advance", advance, setAdvance],
                ["Holding fee", holdingFee, setHoldingFee],
                ["Other security", otherSecurity, setOtherSecurity],
                ["Break fee", breakFee, setBreakFee],
              ] as const
            ).map(([label, value, setter]) => (
              <Field key={label} label={label}>
                <Input
                  type="number"
                  min={0}
                  value={value ?? ""}
                  onChange={(e) =>
                    setter(e.target.value === "" ? null : Number(e.target.value))
                  }
                />
              </Field>
            ))}
          </div>
          <div className="flex gap-2">
            <div className="flex-1">
              <Field label="Start">
                <Input
                  type="date"
                  required
                  value={startDate}
                  onChange={(e) => updateStartDate(e.target.value)}
                />
              </Field>
            </div>
            <div className="flex-1">
              {/* Left blank on purpose: the new term length is the one thing
                  the manager has to decide. */}
              <Field label="End">
                <Input
                  type="date"
                  required
                  value={endDate}
                  onChange={(e) => setEndDate(e.target.value)}
                />
              </Field>
            </div>
          </div>
          <Button type="submit" className="w-full">
            Create renewal
          </Button>
          <Button
            type="button"
            variant="secondary"
            className="w-full"
            onClick={() => router.push(`/app/leases/${leaseId}`)}
          >
            Cancel
          </Button>
        </form>
      </Card>
      <p className="mx-auto mt-4 max-w-2xl">
        <Link href={`/app/leases/${leaseId}`} className="text-brand-fg">
          Back
        </Link>
      </p>
    </AppShell>
  );
}
