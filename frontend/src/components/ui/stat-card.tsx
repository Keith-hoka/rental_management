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
      <p className={`mt-1 text-xl font-semibold ${tone === "danger" ? "text-danger" : "text-text"}`}>
        {value}
      </p>
    </div>
  );
}
