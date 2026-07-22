import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-brand text-white hover:bg-brand-hover",
  secondary: "border border-border bg-surface text-text hover:bg-surface-2",
  ghost: "text-brand hover:bg-brand-soft",
  danger: "border border-border bg-surface text-danger hover:bg-danger-soft",
};

const BASE =
  "inline-flex items-center justify-center gap-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50";

/** Shared classes for a Link that should look like a secondary button. */
export const linkButton = `${BASE} ${VARIANTS.secondary} px-3 py-2`;

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: "sm" | "md";
}

export function Button({ variant = "primary", size = "md", className = "", ...rest }: Props) {
  const sizing = size === "sm" ? "px-2.5 py-1.5 text-xs" : "px-3 py-2";
  return <button className={`${BASE} ${VARIANTS[variant]} ${sizing} ${className}`} {...rest} />;
}
