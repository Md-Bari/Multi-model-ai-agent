export function StatTile({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="rounded-xl border border-border bg-surface p-4">
      <p className="text-xs font-medium text-muted">{label}</p>
      <p className="mt-1.5 text-2xl font-semibold tracking-tight text-foreground tabular-nums">{value}</p>
      {detail && <p className="mt-1 text-xs text-subtle">{detail}</p>}
    </div>
  );
}
