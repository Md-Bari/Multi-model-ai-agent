"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";

import { Badge, Button, Card, EmptyState, ErrorText, Field, Input, PageHeader, Skeleton } from "@/components/ui";
import { api, del, post } from "@/lib/api";
import { fmtDate, fmtRelative, fmtUsd } from "@/lib/format";
import type { ApiKey, CreatedKey } from "@/lib/types";

function status(k: ApiKey) {
  if (k.revoked) return <Badge tone="danger">revoked</Badge>;
  if (k.expires_at && new Date(k.expires_at) < new Date()) return <Badge tone="warning">expired</Badge>;
  if (k.budget_usd !== null && k.spent_usd >= k.budget_usd) return <Badge tone="warning">budget used</Badge>;
  return <Badge tone="good">active</Badge>;
}

export default function KeysPage() {
  const [keys, setKeys] = useState<ApiKey[] | null>(null);
  const [error, setError] = useState("");
  const [created, setCreated] = useState<CreatedKey | null>(null);
  const [copied, setCopied] = useState(false);
  const [form, setForm] = useState({ name: "", rpm: "60", budget: "", days: "" });
  const [creating, setCreating] = useState(false);
  const [formError, setFormError] = useState("");

  const load = useCallback(
    () =>
      api<ApiKey[]>("/api/keys")
        .then(setKeys)
        .catch((e) => setError(e instanceof Error ? e.message : "Failed to load keys")),
    [],
  );

  useEffect(() => {
    let active = true;
    api<ApiKey[]>("/api/keys")
      .then((k) => active && setKeys(k))
      .catch((e) => active && setError(e instanceof Error ? e.message : "Failed to load keys"));
    return () => {
      active = false;
    };
  }, []);

  async function create(e: FormEvent) {
    e.preventDefault();
    setFormError("");
    setCreating(true);
    try {
      const key = await post<CreatedKey>("/api/keys", {
        name: form.name.trim() || "default",
        rpm_limit: Number(form.rpm) || 60,
        budget_usd: form.budget ? Number(form.budget) : null,
        expires_days: form.days ? Number(form.days) : null,
      });
      setCreated(key);
      setCopied(false);
      setForm({ name: "", rpm: "60", budget: "", days: "" });
      load();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Couldn't create key");
    } finally {
      setCreating(false);
    }
  }

  async function revoke(k: ApiKey) {
    if (!confirm(`Revoke "${k.name}"? Apps using it will stop working immediately.`)) return;
    try {
      await del(`/api/keys/${k.id}`);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't revoke key");
    }
  }

  async function copy() {
    if (!created) return;
    await navigator.clipboard.writeText(created.key);
    setCopied(true);
  }

  return (
    <>
      <PageHeader title="API keys" description="Keys your apps use to call the gateway. Each key has its own limits." />

      <div className="space-y-6">
        <Card title="Create a key">
          <form onSubmit={create} className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5 lg:items-end">
            <Field label="Name">
              <Input placeholder="my-app" maxLength={100} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </Field>
            <Field label="Requests per minute">
              <Input type="number" min={1} max={10000} required value={form.rpm} onChange={(e) => setForm({ ...form, rpm: e.target.value })} />
            </Field>
            <Field label="Budget (USD)">
              <Input type="number" min={0.01} step={0.01} placeholder="No limit" value={form.budget} onChange={(e) => setForm({ ...form, budget: e.target.value })} />
            </Field>
            <Field label="Expires in (days)">
              <Input type="number" min={1} max={3650} placeholder="Never" value={form.days} onChange={(e) => setForm({ ...form, days: e.target.value })} />
            </Field>
            <Button type="submit" loading={creating}>
              Create key
            </Button>
          </form>
          <div className="mt-3">
            <ErrorText>{formError}</ErrorText>
          </div>

          {created && (
            <div className="mt-4 rounded-lg border border-good/40 bg-surface-2 p-4">
              <p className="text-sm font-medium">Copy your new key now. You won&apos;t be able to see it again.</p>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <code className="min-w-0 flex-1 rounded-md border border-border bg-surface px-3 py-2 font-mono text-xs break-all">{created.key}</code>
                <Button variant="secondary" onClick={copy}>
                  {copied ? "Copied" : "Copy"}
                </Button>
                <Button variant="ghost" onClick={() => setCreated(null)}>
                  Done
                </Button>
              </div>
              <p className="mt-3 text-xs text-muted">
                Keep it on your server only. Never put it in browser code, a public repo or a screenshot.
              </p>
            </div>
          )}
        </Card>

        <Card title="Your keys">
          <ErrorText>{error}</ErrorText>
          {!keys ? (
            <Skeleton className="h-32" />
          ) : keys.length === 0 ? (
            <EmptyState>No keys yet.</EmptyState>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm whitespace-nowrap">
                <thead className="text-left text-xs text-muted">
                  <tr className="border-b border-border">
                    <th className="py-2 pr-4 font-medium">Name</th>
                    <th className="py-2 pr-4 font-medium">Key</th>
                    <th className="py-2 pr-4 font-medium">Status</th>
                    <th className="py-2 pr-4 text-right font-medium">Limit</th>
                    <th className="py-2 pr-4 text-right font-medium">Spent / budget</th>
                    <th className="py-2 pr-4 font-medium">Last used</th>
                    <th className="py-2 pr-4 font-medium">Expires</th>
                    <th className="py-2" />
                  </tr>
                </thead>
                <tbody>
                  {keys.map((k) => (
                    <tr key={k.id} className="border-b border-border last:border-0">
                      <td className="py-2.5 pr-4 font-medium">{k.name}</td>
                      <td className="py-2.5 pr-4 font-mono text-xs text-muted">{k.prefix}</td>
                      <td className="py-2.5 pr-4">{status(k)}</td>
                      <td className="py-2.5 pr-4 text-right tabular-nums">{k.rpm_limit}/min</td>
                      <td className="py-2.5 pr-4 text-right tabular-nums">
                        {fmtUsd(k.spent_usd)} / {k.budget_usd === null ? "∞" : fmtUsd(k.budget_usd)}
                      </td>
                      <td className="py-2.5 pr-4 text-muted">{fmtRelative(k.last_used_at)}</td>
                      <td className="py-2.5 pr-4 text-muted">{k.expires_at ? fmtDate(k.expires_at) : "Never"}</td>
                      <td className="py-2.5 text-right">
                        {!k.revoked && (
                          <Button variant="danger" className="h-7 px-2.5 text-xs" onClick={() => revoke(k)}>
                            Revoke
                          </Button>
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
    </>
  );
}
