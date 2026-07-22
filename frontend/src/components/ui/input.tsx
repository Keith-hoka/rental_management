import type { InputHTMLAttributes, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";

// border-strong: a field's border is the only thing marking the control.
// focus uses brand-fg, not brand: the brand fill is 2.76:1 on a dark surface,
// so focusing would have made the border fainter than at rest.
const CONTROL =
  "w-full rounded-lg border border-strong bg-surface px-3 py-2 text-sm text-text placeholder:text-muted focus:border-brand-fg focus:outline-none";

export function Input({ className = "", ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={`${CONTROL} ${className}`} {...rest} />;
}

export function Select({ className = "", ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={`${CONTROL} ${className}`} {...rest} />;
}

export function Textarea({ className = "", ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={`${CONTROL} ${className}`} {...rest} />;
}
