"use client";

import { useSyncExternalStore } from "react";

type Theme = "light" | "dark" | "system";

const NEXT: Record<Theme, Theme> = { system: "light", light: "dark", dark: "system" };
const LABEL: Record<Theme, string> = {
  system: "System theme",
  light: "Light theme",
  dark: "Dark theme",
};

// The theme lives on <html>, put there before paint by the script in layout.tsx.
// That makes it external state, so it is read with useSyncExternalStore rather
// than mirrored into a useState inside an effect.
const listeners = new Set<() => void>();

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getSnapshot(): Theme {
  const stored = document.documentElement.dataset.theme;
  return stored === "light" || stored === "dark" ? stored : "system";
}

/** No stored preference is visible while rendering on the server. */
function getServerSnapshot(): Theme {
  return "system";
}

function choose(next: Theme) {
  if (next === "system") {
    localStorage.removeItem("theme");
    delete document.documentElement.dataset.theme;
  } else {
    localStorage.setItem("theme", next);
    document.documentElement.dataset.theme = next;
  }
  listeners.forEach((listener) => listener());
}

/**
 * Cycles system -> light -> dark. "system" means no stored preference, so the
 * media query in globals.css decides; the other two stamp data-theme on <html>,
 * which the same stylesheet treats as the override.
 */
export function ThemeToggle({ className = "" }: { className?: string }) {
  const theme = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  return (
    <button
      onClick={() => choose(NEXT[theme])}
      className={`rounded-lg px-3 py-2 text-sm font-medium text-muted hover:bg-surface-2 hover:text-text ${className}`}
    >
      {LABEL[theme]}
    </button>
  );
}
