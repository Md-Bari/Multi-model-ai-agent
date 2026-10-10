"use client";

import { useCallback, useEffect, useState } from "react";

import { RequestsChart } from "@/components/requests-chart";
import { StatTile } from "@/components/stat-tile";
import { Badge, Button, Card, EmptyState, ErrorText, PageHeader, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { fmtCompact, fmtNumber, fmtRelative, fmtUsd } from "@/lib/format";
import type { Providers, Usage } from "@/lib/types";

const fetchAll = () => Promise.all([api<Usage>("/api/usage"), api<Providers>("/api/providers")]);

export default function DashboardPage() {
  const [usage, setUsage] = useState<Usage | null>(null);
  const [providers, setProviders] = useState<Providers | null>(null);
  const [error, setError] = useState("");
  const [refreshing, setRefreshing] = useState(false);

  const apply = useCallback((u: Usage, p: Providers) => {
    setUsage(u);
    setProviders(p);
    setError("");
  }, []);
  const fail = useCallback((e: unknown) => setError(e instanceof Error ? e.message : "Failed to load"), []);

  useEffect(() => {
    let active = true;
    fetchAll()
      .then(([u, p]) => active && apply(u, p))
      .catch((e) => active && fail(e));
    return () => {
      active = false;
    };
  }, [apply, fail]);

  function refresh() {
    setRefreshing(true);
    fetchAll()
      .then(([u, p]) => apply(u, p))
      .catch(fail)
      .finally(() => setRefreshing(false));
  }

  const t = usage?.totals;
  const hitRate = t && t.requests ? Math.round((t.cache_hits / t.requests) * 100) : 0;

  return (
    <>
      <PageHeader
        title="Overview"
        description="Requests, tokens and cost across all your keys."
        action={
          <Button variant="secondary" onClick={refresh} loading={refreshing}>
            Refresh
          </Button>
        }
      />
      <ErrorText>{error}</ErrorText>

      {!usage ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      ) : (
        <div className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatTile label="Requests" value={fmtNumber(t!.requests)} detail={t!.errors ? `${t!.errors} failed` : "No failures"} />
            <StatTile
              label="Tokens"
              value={fmtCompact(t!.prompt_tokens + t!.completion_tokens)}
              detail={`${fmtCompact(t!.prompt_tokens)} in · ${fmtCompact(t!.completion_tokens)} out`}
            />
            <StatTile label="Total cost" value={fmtUsd(t!.cost_usd)} detail="At list prices" />
            <StatTile label="Cache hit rate" value={`${hitRate}%`} detail={`Avg latency ${fmtNumber(t!.avg_latency_ms)} ms`} />
          </div>

          <div className="grid gap-6 lg:grid-cols-3">
            <Card title="Requests per day" className="lg:col-span-2">
              <RequestsChart daily={usage.daily} />
            </Card>
            <Card title="Routing">
              {providers && (
                <div className="space-y-4 text-sm">
                  {(["cheap", "strong"] as const).map((tier) => (
                    <div key={tier}>
                      <p className="mb-1.5 text-xs font-medium text-muted">{tier === "cheap" ? "Simple questions" : "Coding and hard questions"}</p>
                      {providers[tier].length === 0 ? (
                        <p className="text-subtle">No provider configured</p>
                      ) : (
                        <ol className="space-y-1">
                          {providers[tier].map((d, i) => (
                            <li key={d.name} className="flex items-center gap-2">
                              <span className="w-14 text-xs text-subtle">{i === 0 ? "primary" : "fallback"}</span>
                              <code className="truncate font-mono text-xs">{d.model}</code>
                            </li>
                          ))}
                        </ol>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </div>

          <Card title="By model">
            {usage.by_model.length === 0 ? (
              <EmptyState>No requests yet. Create a key or try the playground.</EmptyState>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-left text-xs text-muted">
                    <tr className="border-b border-border">
                      <th className="py-2 pr-4 font-medium">Model</th>
                      <th className="py-2 pr-4 text-right font-medium">Requests</th>
                      <th className="py-2 pr-4 text-right font-medium">Tokens</th>
                      <th className="py-2 text-right font-medium">Cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {usage.by_model.map((m) => (
                      <tr key={m.model} className="border-b border-border last:border-0">
                        <td className="py-2 pr-4 font-mono text-xs">{m.model}</td>
                        <td className="py-2 pr-4 text-right tabular-nums">{fmtNumber(m.requests)}</td>
                        <td className="py-2 pr-4 text-right tabular-nums">{fmtNumber(m.tokens)}</td>
                        <td className="py-2 text-right tabular-nums">{fmtUsd(m.cost_usd)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          <Card title="Recent requests">
            {usage.recent.length === 0 ? (
              <EmptyState>Nothing here yet.</EmptyState>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm whitespace-nowrap">
                  <thead className="text-left text-xs text-muted">
                    <tr className="border-b border-border">
                      <th className="py-2 pr-4 font-medium">When</th>
                      <th className="py-2 pr-4 font-medium">Source</th>
                      <th className="py-2 pr-4 font-medium">Tier</th>
                      <th className="py-2 pr-4 font-medium">Model</th>
                      <th className="py-2 pr-4 text-right font-medium">Tokens</th>
                      <th className="py-2 pr-4 text-right font-medium">Cost</th>
                      <th className="py-2 pr-4 text-right font-medium">Latency</th>
                      <th className="py-2 font-medium">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {usage.recent.map((r) => (
                      <tr key={r.id} className="border-b border-border last:border-0">
                        <td className="py-2 pr-4 text-muted">{fmtRelative(r.created_at)}</td>
                        <td className="py-2 pr-4 text-muted">{r.key_id ? `key #${r.key_id}` : "playground"}</td>
                        <td className="py-2 pr-4">{r.tier}</td>
                        <td className="py-2 pr-4 font-mono text-xs">{r.model}</td>
                        <td className="py-2 pr-4 text-right tabular-nums">{fmtNumber(r.prompt_tokens + r.completion_tokens)}</td>
                        <td className="py-2 pr-4 text-right tabular-nums">{fmtUsd(r.cost_usd)}</td>
                        <td className="py-2 pr-4 text-right tabular-nums">{fmtNumber(r.latency_ms)} ms</td>
                        <td className="py-2">
                          {r.status !== "ok" ? (
                            <Badge tone="danger">failed</Badge>
                          ) : r.cached ? (
                            <Badge tone="accent">cached</Badge>
                          ) : (
                            <Badge tone="good">ok</Badge>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
      )}
    </>
  );
}
