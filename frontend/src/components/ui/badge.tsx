import type { ReactNode } from "react";

type Tone = "neutral" | "brand" | "success" | "warning" | "danger";

const TONES: Record<Tone, string> = {
  neutral: "bg-surface-2 text-muted",
  brand: "bg-brand-soft text-brand-on-soft",
  success: "bg-success-soft text-success-on-soft",
  warning: "bg-warning-soft text-warning-on-soft",
  danger: "bg-danger-soft text-danger-on-soft",
};

export function Badge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${TONES[tone]}`}>
      {children}
    </span>
  );
}
