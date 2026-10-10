"use client";

import { useMemo, useState } from "react";

import { fmtDay, fmtNumber, fmtUsd } from "@/lib/format";
import type { Usage } from "@/lib/types";

type Day = Usage["daily"][number];

const HEIGHT = 160;
const BAR_MAX = 24; // bars never fill the slot; leftover is air
const GAP = 2;

/** Fills missing days with zero so the x-axis is continuous. */
function lastNDays(daily: Day[], n: number): Day[] {
  const byDate = new Map(daily.map((d) => [d.date, d]));
  const out: Day[] = [];
  const today = new Date();
  for (let i = n - 1; i >= 0; i--) {
    const d = new Date(today.getFullYear(), today.getMonth(), today.getDate() - i);
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    out.push(byDate.get(key) ?? { date: key, requests: 0, cost_usd: 0 });
  }
  return out;
}

/** Requests per day: a single series, so no legend; the card title names it. */
export function RequestsChart({ daily, days = 14 }: { daily: Day[]; days?: number }) {
  const data = useMemo(() => lastNDays(daily, days), [daily, days]);
  const [hover, setHover] = useState<number | null>(null);
  const max = Math.max(1, ...data.map((d) => d.requests));
  const peak = data.reduce((best, d, i) => (d.requests > data[best].requests ? i : best), 0);

  return (
    <div className="relative">
      <div className="relative flex items-end" style={{ height: HEIGHT, gap: GAP }} onMouseLeave={() => setHover(null)}>
        {/* recessive gridlines */}
        {[0.5, 1].map((f) => (
          <div key={f} aria-hidden className="pointer-events-none absolute inset-x-0 border-t border-[var(--chart-grid)]" style={{ bottom: f * HEIGHT }} />
        ))}
        {data.map((d, i) => {
          const h = d.requests === 0 ? 0 : Math.max(3, (d.requests / max) * (HEIGHT - 20));
          return (
            <div
              key={d.date}
              className="relative flex h-full flex-1 cursor-default items-end justify-center"
              onMouseEnter={() => setHover(i)}
              onFocus={() => setHover(i)}
              onBlur={() => setHover(null)}
              tabIndex={0}
              aria-label={`${fmtDay(d.date)}: ${d.requests} requests`}
            >
              {i === peak && d.requests > 0 && (
                <span className="absolute text-[11px] font-medium text-muted tabular-nums" style={{ bottom: h + 4 }}>
                  {fmtNumber(d.requests)}
                </span>
              )}
              <div
                className="w-full rounded-t-[4px] transition-opacity"
                style={{
                  height: h,
                  maxWidth: BAR_MAX,
                  background: "var(--chart-bar)",
                  opacity: hover === null || hover === i ? 1 : 0.45,
                }}
              />
            </div>
          );
        })}
      </div>
      <div className="mt-2 flex justify-between text-[11px] text-subtle">
        <span>{fmtDay(data[0].date)}</span>
        <span>{fmtDay(data[data.length - 1].date)}</span>
      </div>

      {hover !== null && (
        <div
          role="tooltip"
          className="pointer-events-none absolute top-0 z-10 -translate-x-1/2 rounded-md border border-border bg-surface px-2.5 py-1.5 text-xs shadow-sm"
          style={{ left: `${((hover + 0.5) / data.length) * 100}%` }}
        >
          <p className="font-medium text-foreground">{fmtDay(data[hover].date)}</p>
          <p className="text-muted tabular-nums">
            {fmtNumber(data[hover].requests)} requests · {fmtUsd(data[hover].cost_usd)}
          </p>
        </div>
      )}

      {/* table view for screen readers */}
      <table className="sr-only">
        <caption>Requests per day</caption>
        <thead>
          <tr>
            <th>Date</th>
            <th>Requests</th>
            <th>Cost</th>
          </tr>
        </thead>
        <tbody>
          {data.map((d) => (
            <tr key={d.date}>
              <td>{d.date}</td>
              <td>{d.requests}</td>
              <td>{fmtUsd(d.cost_usd)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
