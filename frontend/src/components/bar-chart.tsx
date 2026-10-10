"use client";

import { useState } from "react";

export interface Series {
  key: string;
  label: string;
  color: string; // CSS color, typically a var(--chart-*) token
}

export interface BarChartProps<T> {
  data: T[];
  series: Series[]; // bottom to top
  value: (row: T, seriesKey: string) => number;
  label: (row: T) => string; // full label (tooltip, table)
  tick: (row: T) => string; // short axis label
  format?: (n: number) => string;
  caption: string;
  height?: number;
  showTable?: boolean;
}

const BAR_MAX = 24; // bars never fill the slot; leftover is air
const GAP = 2; // surface-colored gap between stacked segments and adjacent bars

function niceMax(n: number): number {
  if (n <= 0) return 1;
  const magnitude = 10 ** Math.floor(Math.log10(n));
  const step = [1, 2, 2.5, 5, 10].find((s) => s * magnitude >= n) ?? 10;
  return step * magnitude;
}

/** Stacked column chart with hover tooltip, legend (for 2+ series) and a table view. */
export function BarChart<T>({ data, series, value, label, tick, format = String, caption, height = 180, showTable = false }: BarChartProps<T>) {
  const [hover, setHover] = useState<number | null>(null);
  const totals = data.map((row) => series.reduce((sum, s) => sum + value(row, s.key), 0));
  const max = niceMax(Math.max(...totals, 0));
  const tickEvery = Math.ceil(data.length / 7);

  if (showTable) {
    return (
      <div className="max-h-80 overflow-auto">
        <table className="w-full text-sm">
          <caption className="sr-only">{caption}</caption>
          <thead className="sticky top-0 bg-surface text-left text-xs text-muted">
            <tr className="border-b border-border">
              <th className="py-2 pr-4 font-medium">Period</th>
              {series.map((s) => (
                <th key={s.key} className="py-2 pr-4 text-right font-medium">
                  {s.label}
                </th>
              ))}
              {series.length > 1 && <th className="py-2 text-right font-medium">Total</th>}
            </tr>
          </thead>
          <tbody>
            {data.map((row, i) => (
              <tr key={i} className="border-b border-border last:border-0">
                <td className="py-1.5 pr-4 text-muted">{label(row)}</td>
                {series.map((s) => (
                  <td key={s.key} className="py-1.5 pr-4 text-right tabular-nums">
                    {format(value(row, s.key))}
                  </td>
                ))}
                {series.length > 1 && <td className="py-1.5 text-right font-medium tabular-nums">{format(totals[i])}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <div>
      {series.length > 1 && (
        <ul className="mb-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
          {series.map((s) => (
            <li key={s.key} className="flex items-center gap-1.5">
              <span aria-hidden className="size-2.5 rounded-[3px]" style={{ background: s.color }} />
              {s.label}
            </li>
          ))}
        </ul>
      )}

      <div className="relative flex gap-2">
        {/* y-axis: recessive, two labels */}
        <div className="flex w-10 shrink-0 flex-col justify-between text-right text-[11px] text-subtle tabular-nums" style={{ height }}>
          <span>{format(max)}</span>
          <span>{format(max / 2)}</span>
          <span>0</span>
        </div>

        <div className="relative min-w-0 flex-1">
          <div className="relative flex items-end" style={{ height, gap: GAP }} onMouseLeave={() => setHover(null)}>
            {[0.5, 1].map((f) => (
              <div key={f} aria-hidden className="pointer-events-none absolute inset-x-0 border-t border-[var(--chart-grid)]" style={{ bottom: f * height }} />
            ))}
            <div aria-hidden className="pointer-events-none absolute inset-x-0 bottom-0 border-t border-border" />

            {data.map((row, i) => (
              <div
                key={i}
                tabIndex={0}
                aria-label={`${label(row)}: ${series.map((s) => `${s.label} ${format(value(row, s.key))}`).join(", ")}`}
                className="relative flex h-full flex-1 cursor-default flex-col items-center justify-end outline-none"
                onMouseEnter={() => setHover(i)}
                onFocus={() => setHover(i)}
                onBlur={() => setHover(null)}
              >
                <div
                  className="flex w-full flex-col-reverse overflow-hidden rounded-t-[4px] transition-opacity"
                  style={{ maxWidth: BAR_MAX, gap: totals[i] ? GAP : 0, opacity: hover === null || hover === i ? 1 : 0.45 }}
                >
                  {series.map((s) => {
                    const v = value(row, s.key);
                    if (!v) return null;
                    return <div key={s.key} style={{ height: Math.max(2, (v / max) * height - GAP), background: s.color }} />;
                  })}
                </div>
              </div>
            ))}
          </div>

          {/* every Nth label, centred under its bar; never truncated */}
          <div aria-hidden className="relative mt-2 h-4 text-[11px] text-subtle">
            {data.map((row, i) =>
              (data.length - 1 - i) % tickEvery === 0 ? (
                <span key={i} className="absolute -translate-x-1/2 whitespace-nowrap" style={{ left: `${((i + 0.5) / data.length) * 100}%` }}>
                  {tick(row)}
                </span>
              ) : null,
            )}
          </div>

          {hover !== null && (
            <div
              role="tooltip"
              className="pointer-events-none absolute top-0 z-10 min-w-36 rounded-md border border-border bg-surface px-3 py-2 text-xs shadow-md"
              style={{
                left: `${((hover + 0.5) / data.length) * 100}%`,
                transform: `translateX(${hover / data.length > 0.6 ? "-105%" : "5%"})`,
              }}
            >
              <p className="mb-1 font-medium text-foreground">{label(data[hover])}</p>
              {[...series].reverse().map((s) => (
                <p key={s.key} className="flex items-center justify-between gap-4 text-muted">
                  <span className="flex items-center gap-1.5">
                    <span aria-hidden className="size-2 rounded-[2px]" style={{ background: s.color }} />
                    {s.label}
                  </span>
                  <span className="text-foreground tabular-nums">{format(value(data[hover], s.key))}</span>
                </p>
              ))}
              {series.length > 1 && (
                <p className="mt-1 flex justify-between gap-4 border-t border-border pt-1 text-muted">
                  Total <span className="font-medium text-foreground tabular-nums">{format(totals[hover])}</span>
                </p>
              )}
            </div>
          )}
        </div>
      </div>

      {/* table view for screen readers */}
      <table className="sr-only">
        <caption>{caption}</caption>
        <tbody>
          {data.map((row, i) => (
            <tr key={i}>
              <th>{label(row)}</th>
              {series.map((s) => (
                <td key={s.key}>
                  {s.label}: {value(row, s.key)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
