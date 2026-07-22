"use client";

import { useSyncExternalStore } from "react";

type Theme = "light" | "dark";

const DARK_QUERY = "(prefers-color-scheme: dark)";

// The theme lives on <html>, put there before paint by the script in layout.tsx.
// That makes it external state, so it is read with useSyncExternalStore rather
// than mirrored into a useState inside an effect.
const listeners = new Set<() => void>();

function subscribe(listener: () => void) {
  listeners.add(listener);
  // With no stored preference the OS still decides, so track it changing.
  const media = window.matchMedia(DARK_QUERY);
  media.addEventListener("change", listener);
  return () => {
    listeners.delete(listener);
    media.removeEventListener("change", listener);
  };
}

/** What the page is actually showing: the explicit choice, else the OS. */
function getSnapshot(): Theme {
  const chosen = document.documentElement.dataset.theme;
  if (chosen === "light" || chosen === "dark") return chosen;
  return window.matchMedia(DARK_QUERY).matches ? "dark" : "light";
}

/** No preference and no media query are visible while rendering on the server. */
function getServerSnapshot(): Theme {
  return "light";
}

function choose(next: Theme) {
  localStorage.setItem("theme", next);
  document.documentElement.dataset.theme = next;
  listeners.forEach((listener) => listener());
}

const ICONS: Record<Theme, React.ReactNode> = {
  // Showing the destination, not the current state: in light mode you see the
  // moon you are about to switch to.
  light: (
    <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z" />
  ),
  dark: (
    <>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </>
  ),
};

export function ThemeToggle({ className = "" }: { className?: string }) {
  const theme = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  const next: Theme = theme === "light" ? "dark" : "light";

  return (
    <button
      onClick={() => choose(next)}
      aria-label={`Switch to ${next} mode`}
      title={`Switch to ${next} mode`}
      className={`flex h-8 w-8 items-center justify-center rounded-full border border-border text-text hover:bg-surface-2 ${className}`}
    >
      <svg
        viewBox="0 0 24 24"
        width="16"
        height="16"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        {ICONS[theme]}
      </svg>
    </button>
  );
}
