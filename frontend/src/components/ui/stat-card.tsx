export function StatCard({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: string;
  tone?: "default" | "danger";
}) {
  return (
    <div className="rounded-xl border border-border bg-surface p-4 shadow-[var(--shadow-card)]">
      <p className="text-xs text-muted">{label}</p>
      {/* break-words so a long value wraps instead of spilling past the corners. */}
      <p
        className={`mt-1 text-xl font-semibold break-words ${
          tone === "danger" ? "text-danger" : "text-text"
        }`}
      >
        {value}
      </p>
    </div>
  );
}
