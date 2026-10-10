"use client";

import { useEffect, useState } from "react";

import { BarChart, type Series } from "@/components/bar-chart";
import { StatTile } from "@/components/stat-tile";
import { Badge, Button, Card, EmptyState, ErrorText, PageHeader, Skeleton, cn } from "@/components/ui";
import { api } from "@/lib/api";
import { fmtBucket, fmtBucketTick, fmtCompact, fmtNumber, fmtUsd } from "@/lib/format";
import type { KeyLimit, Timeseries, UsageRange } from "@/lib/types";

const RANGES: { value: UsageRange; label: string }[] = [
  { value: "24h", label: "24 hours" },
  { value: "7d", label: "7 days" },
  { value: "28d", label: "28 days" },
  { value: "90d", label: "90 days" },
];

// Bottom to top. Red only touches blue, which keeps the stack colorblind-safe.
const REQUEST_SERIES: Series[] = [
  { key: "cached", label: "Cached", color: "var(--chart-cached)" },
  { key: "fresh", label: "Model calls", color: "var(--chart-fresh)" },
  { key: "errors", label: "Failed", color: "var(--chart-failed)" },
];
const TOKEN_SERIES: Series[] = [
  { key: "input_tokens", label: "Input tokens", color: "var(--chart-input)" },
  { key: "output_tokens", label: "Output tokens", color: "var(--chart-output)" },
];

type Bucket = Timeseries["buckets"][number];

function requestValue(b: Bucket, key: string): number {
  if (key === "fresh") return Math.max(0, b.requests - b.cached - b.errors);
  return b[key as "cached" | "errors"];
}

const tzOffset = () => -new Date().getTimezoneOffset();

function Select({ label, value, onChange, children }: { label: string; value: string; onChange: (v: string) => void; children: React.ReactNode }) {
  return (
    <label className="flex items-center gap-2 text-sm">
      <span className="text-muted">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-9 rounded-md border border-border bg-surface px-2.5 text-sm text-foreground focus:border-accent focus:ring-2 focus:ring-accent/25 focus:outline-none"
      >
        {children}
      </select>
    </label>
  );
}

function ChartCard({ title, children }: { title: string; children: (showTable: boolean) => React.ReactNode }) {
  const [table, setTable] = useState(false);
  return (
    <Card
      title={title}
      action={
        <div className="flex rounded-md border border-border p-0.5 text-xs" role="radiogroup" aria-label={`${title} view`}>
          {(["Chart", "Table"] as const).map((v) => (
            <button
              key={v}
              role="radio"
              aria-checked={table === (v === "Table")}
              onClick={() => setTable(v === "Table")}
              className={cn("rounded px-2 py-0.5", table === (v === "Table") ? "bg-surface-2 font-medium text-foreground" : "text-muted")}
            >
              {v}
            </button>
          ))}
        </div>
      }
    >
      {children(table)}
    </Card>
  );
}

function LimitMeter({ used, limit }: { used: number; limit: number }) {
  const pct = Math.min(100, Math.round((used / limit) * 100));
  const tone = pct >= 100 ? "danger" : pct >= 80 ? "warning" : null;
  return (
    <div className="flex items-center gap-3">
      <div className="h-1.5 w-28 overflow-hidden rounded-full bg-surface-2" role="meter" aria-valuenow={used} aria-valuemin={0} aria-valuemax={limit}>
        <div className="h-full rounded-full" style={{ width: `${pct}%`, background: tone === "danger" ? "var(--danger)" : tone === "warning" ? "var(--warning)" : "var(--accent)" }} />
      </div>
      <span className="text-xs tabular-nums">
        {used} / {limit}
      </span>
      {tone && <Badge tone={tone}>{tone === "danger" ? "at limit" : "near limit"}</Badge>}
    </div>
  );
}

export default function UsagePage() {
  const [range, setRange] = useState<UsageRange>("7d");
  const [model, setModel] = useState("");
  const [key, setKey] = useState("");
  const [refreshTick, setRefreshTick] = useState(0);
  const query = new URLSearchParams({ range, ...(model && { model }), ...(key && { key }) }).toString();

  // Data is stored with the query it answers, so "loading" is derived instead of set in the effect.
  const [result, setResult] = useState<{ query: string; data?: Timeseries; error?: string } | null>(null);
  const [limits, setLimits] = useState<KeyLimit[] | null>(null);

  useEffect(() => {
    let active = true;
    // The viewer's time zone is read here, not during render (pages are prerendered).
    api<Timeseries>(`/api/usage/timeseries?${query}&tz_offset=${tzOffset()}`)
      .then((data) => active && setResult({ query, data }))
      .catch((e) => active && setResult({ query, error: e instanceof Error ? e.message : "Failed to load usage" }));
    return () => {
      active = false;
    };
  }, [query, refreshTick]);

  // Live rate-limit usage, refreshed every 10s while the page is visible.
  useEffect(() => {
    let active = true;
    const load = () =>
      api<KeyLimit[]>("/api/usage/limits")
        .then((l) => active && setLimits(l))
        .catch(() => undefined);
    load();
    const id = setInterval(load, 10_000);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, [refreshTick]);

  const data = result?.data;
  const loading = !result || result.query !== query;
  const t = data?.totals;
  const unit = data?.unit ?? "day";
  const hitRate = t && t.requests ? Math.round((t.cached / t.requests) * 100) : 0;

  return (
    <>
      <PageHeader
        title="Usage"
        description="Requests and tokens over time, across your API keys and the playground."
        action={
          <div className="flex items-center gap-1 rounded-lg border border-border bg-surface p-1" role="radiogroup" aria-label="Time range">
            {RANGES.map((r) => (
              <button
                key={r.value}
                role="radio"
                aria-checked={range === r.value}
                onClick={() => setRange(r.value)}
                className={cn(
                  "rounded-md px-3 py-1 text-sm transition",
                  range === r.value ? "bg-surface-2 font-medium text-foreground" : "text-muted hover:text-foreground",
                )}
              >
                {r.label}
              </button>
            ))}
          </div>
        }
      />

      <div className="mb-6 flex flex-wrap items-center gap-4">
        <Select label="Model" value={model} onChange={setModel}>
          <option value="">All models</option>
          {data?.filters.models.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </Select>
        <Select label="Source" value={key} onChange={setKey}>
          <option value="">All keys and playground</option>
          <option value="playground">Playground</option>
          {data?.filters.keys.map((k) => (
            <option key={k.id} value={String(k.id)}>
              {k.name} (#{k.id})
            </option>
          ))}
        </Select>
        <Button variant="secondary" onClick={() => setRefreshTick((n) => n + 1)} loading={loading && !!result}>
          Refresh
        </Button>
      </div>

      <ErrorText>{result?.error}</ErrorText>

      {!data ? (
        <div className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
            {[0, 1, 2, 3, 4].map((i) => (
              <Skeleton key={i} className="h-24" />
            ))}
          </div>
          <Skeleton className="h-64" />
        </div>
      ) : (
        <div className={cn("space-y-6 transition-opacity", loading && "opacity-60")}>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
            <StatTile label="Requests" value={fmtNumber(t!.requests)} detail={t!.errors ? `${fmtNumber(t!.errors)} failed` : "No failures"} />
            <StatTile label="Input tokens" value={fmtCompact(t!.input_tokens)} />
            <StatTile label="Output tokens" value={fmtCompact(t!.output_tokens)} />
            <StatTile label="Cache hits" value={fmtNumber(t!.cached)} detail={`${hitRate}% of requests`} />
            <StatTile label="Cost" value={fmtUsd(t!.cost_usd)} detail="At list prices" />
          </div>

          <div className="grid gap-6 xl:grid-cols-2">
            <ChartCard title={unit === "hour" ? "Requests per hour" : "Requests per day"}>
              {(showTable) => (
                <BarChart
                  data={data.buckets}
                  series={REQUEST_SERIES}
                  value={requestValue}
                  label={(b) => fmtBucket(b.t, unit)}
                  tick={(b) => fmtBucketTick(b.t, unit)}
                  format={(n) => fmtCompact(Math.round(n))}
                  caption="Requests over time"
                  showTable={showTable}
                />
              )}
            </ChartCard>
            <ChartCard title={unit === "hour" ? "Tokens per hour" : "Tokens per day"}>
              {(showTable) => (
                <BarChart
                  data={data.buckets}
                  series={TOKEN_SERIES}
                  value={(b, k) => b[k as "input_tokens" | "output_tokens"]}
                  label={(b) => fmtBucket(b.t, unit)}
                  tick={(b) => fmtBucketTick(b.t, unit)}
                  format={(n) => fmtCompact(Math.round(n))}
                  caption="Tokens over time"
                  showTable={showTable}
                />
              )}
            </ChartCard>
          </div>

          <Card title="Rate limits (live)">
            {!limits ? (
              <Skeleton className="h-20" />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm whitespace-nowrap">
                  <thead className="text-left text-xs text-muted">
                    <tr className="border-b border-border">
                      <th className="py-2 pr-4 font-medium">Source</th>
                      <th className="py-2 pr-4 font-medium">Requests this minute</th>
                      <th className="py-2 pr-4 text-right font-medium">Requests (24h)</th>
                      <th className="py-2 pr-4 text-right font-medium">Tokens (24h)</th>
                      <th className="py-2 text-right font-medium">Spent / budget</th>
                    </tr>
                  </thead>
                  <tbody>
                    {limits.map((l) => (
                      <tr key={l.key_id ?? "playground"} className="border-b border-border last:border-0">
                        <td className="py-2.5 pr-4 font-medium">{l.name}</td>
                        <td className="py-2.5 pr-4">
                          <LimitMeter used={l.requests_this_minute} limit={l.rpm_limit} />
                        </td>
                        <td className="py-2.5 pr-4 text-right tabular-nums">{fmtNumber(l.requests_24h)}</td>
                        <td className="py-2.5 pr-4 text-right tabular-nums">{fmtCompact(l.tokens_24h)}</td>
                        <td className="py-2.5 text-right tabular-nums">
                          {l.spent_usd === null ? "—" : `${fmtUsd(l.spent_usd)} / ${l.budget_usd === null ? "∞" : fmtUsd(l.budget_usd)}`}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          <div className="space-y-6">
            <Card title="By model">
              {data.by_model.length === 0 ? (
                <EmptyState>No requests in this period.</EmptyState>
              ) : (
                <BreakdownTable rows={data.by_model.map((m) => ({ ...m, id: m.model, name: m.model, mono: true }))} />
              )}
            </Card>
            <Card title="By source">
              {data.by_key.length === 0 ? (
                <EmptyState>No requests in this period.</EmptyState>
              ) : (
                <BreakdownTable rows={data.by_key.map((k) => ({ ...k, id: String(k.key_id ?? "playground"), mono: false }))} />
              )}
            </Card>
          </div>
        </div>
      )}
    </>
  );
}

function BreakdownTable({
  rows,
}: {
  rows: { id: string; name: string; mono: boolean; requests: number; cached: number; errors: number; input_tokens: number; output_tokens: number; cost_usd: number; avg_latency_ms: number }[];
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm whitespace-nowrap">
        <thead className="text-left text-xs text-muted">
          <tr className="border-b border-border">
            <th className="py-2 pr-4 font-medium">Name</th>
            <th className="py-2 pr-4 text-right font-medium">Requests</th>
            <th className="py-2 pr-4 text-right font-medium">Input</th>
            <th className="py-2 pr-4 text-right font-medium">Output</th>
            <th className="py-2 pr-4 text-right font-medium">Cached</th>
            <th className="py-2 pr-4 text-right font-medium">Failed</th>
            <th className="py-2 pr-4 text-right font-medium">Avg latency</th>
            <th className="py-2 text-right font-medium">Cost</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className="border-b border-border last:border-0">
              <td className={cn("py-2 pr-4", r.mono ? "font-mono text-xs" : "font-medium")}>{r.name}</td>
              <td className="py-2 pr-4 text-right tabular-nums">{fmtNumber(r.requests)}</td>
              <td className="py-2 pr-4 text-right tabular-nums">{fmtCompact(r.input_tokens)}</td>
              <td className="py-2 pr-4 text-right tabular-nums">{fmtCompact(r.output_tokens)}</td>
              <td className="py-2 pr-4 text-right tabular-nums">{fmtNumber(r.cached)}</td>
              <td className="py-2 pr-4 text-right tabular-nums">{fmtNumber(r.errors)}</td>
              <td className="py-2 pr-4 text-right tabular-nums">{r.avg_latency_ms ? `${fmtNumber(r.avg_latency_ms)} ms` : "—"}</td>
              <td className="py-2 text-right tabular-nums">{fmtUsd(r.cost_usd)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
