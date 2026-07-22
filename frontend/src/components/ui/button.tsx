import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "ghost" | "outline" | "danger";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-brand text-white hover:bg-brand-hover",
  // border-strong, not border-border: these have no fill, so the border is the
  // only thing marking the control, and the divider token is too faint for that.
  secondary: "border border-strong bg-surface text-text hover:bg-surface-2",
  ghost: "text-brand-fg hover:bg-brand-soft",
  outline: "border border-strong text-brand-fg hover:bg-brand-soft",
  danger: "border border-strong bg-surface text-danger hover:bg-danger-soft",
};

// whitespace-nowrap + shrink-0: as a flex item a button is shrinkable by
// default, which squeezes its label onto several lines instead of keeping the
// control intact.
const BASE =
  "inline-flex shrink-0 items-center justify-center gap-2 rounded-lg text-sm font-medium whitespace-nowrap transition-colors disabled:opacity-50";

/**
 * Shared classes for a Link that acts as a page's primary action, so those
 * links match the primary Button instead of looking like a separate species.
 */
export const linkButton = `${BASE} ${VARIANTS.primary} px-3 py-2`;

/** Same shape, for a Link that is a secondary action beside a primary one. */
export const linkButtonSecondary = `${BASE} ${VARIANTS.secondary} px-3 py-2`;

/** Same shape, for a quiet in-card Link: brand text, no border or fill. */
export const linkButtonGhost = `${BASE} ${VARIANTS.ghost} px-3 py-2`;

/**
 * Outlined brand-text action. Shared by the "Open lease" link and the file
 * pickers, which are <label>s and so cannot be Buttons.
 */
export const linkButtonOutline = `${BASE} ${VARIANTS.outline} px-3 py-2`;

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: "sm" | "md";
}

export function Button({ variant = "primary", size = "md", className = "", ...rest }: Props) {
  const sizing = size === "sm" ? "px-2.5 py-1.5 text-xs" : "px-3 py-2";
  return <button className={`${BASE} ${VARIANTS[variant]} ${sizing} ${className}`} {...rest} />;
}
