const number = new Intl.NumberFormat("en-US");
const compact = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });

export const fmtNumber = (n: number) => number.format(n);
export const fmtCompact = (n: number) => (n < 10_000 ? number.format(n) : compact.format(n));

export function fmtUsd(n: number): string {
  if (n === 0) return "$0";
  if (n < 0.01) return `$${n.toFixed(4)}`;
  return `$${n.toFixed(2)}`;
}

export function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function fmtRelative(iso: string | null): string {
  if (!iso) return "never";
  const seconds = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

export function fmtDay(isoDate: string): string {
  return new Date(`${isoDate}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/** Bucket labels from the usage API: "YYYY-MM-DDTHH:00" (hourly) or "YYYY-MM-DD" (daily), local time. */
export function fmtBucket(t: string, unit: "hour" | "day"): string {
  if (unit === "day") return fmtDay(t);
  const d = new Date(`${t}:00`);
  return `${d.toLocaleDateString(undefined, { month: "short", day: "numeric" })}, ${d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}`;
}

export function fmtBucketTick(t: string, unit: "hour" | "day"): string {
  if (unit === "day") return fmtDay(t);
  return new Date(`${t}:00`).toLocaleTimeString(undefined, { hour: "numeric" });
}
