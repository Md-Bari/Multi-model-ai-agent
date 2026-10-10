"use client";

import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import { Badge, Button, ErrorText, PageHeader, cn } from "@/components/ui";
import { streamChat, type StreamMeta } from "@/lib/stream";
import type { ChatMessage } from "@/lib/types";

const MODES = [
  { value: "auto", label: "Auto" },
  { value: "cheap", label: "Fast" },
  { value: "strong", label: "Strong" },
];

export default function PlaygroundPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [mode, setMode] = useState("auto");
  const [meta, setMeta] = useState<StreamMeta | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  // Stop an in-flight stream if the page is hidden or left.
  useEffect(() => () => abortRef.current?.abort(), []);

  async function send(e?: FormEvent) {
    e?.preventDefault();
    const text = input.trim();
    if (!text || busy) return;

    const history: ChatMessage[] = [...messages, { role: "user", content: text }];
    setMessages([...history, { role: "assistant", content: "" }]);
    setInput("");
    setError("");
    setMeta(null);
    setBusy(true);

    const controller = new AbortController();
    abortRef.current = controller;
    try {
      for await (const delta of streamChat({ model: mode, messages: history }, controller.signal, setMeta)) {
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          next[next.length - 1] = { ...last, content: last.content + delta };
          return next;
        });
      }
    } catch (err) {
      if (!controller.signal.aborted) {
        setError(err instanceof Error ? err.message : "Request failed");
        // Drop the empty assistant bubble on failure.
        setMessages((prev) => (prev[prev.length - 1]?.content ? prev : prev.slice(0, -1)));
      }
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  return (
    <div className="flex h-[calc(100dvh-7rem)] flex-col sm:h-[calc(100dvh-8rem)]">
      <PageHeader
        title="Playground"
        description="Try the gateway with your account. Requests count toward your usage."
        action={
          <div className="flex items-center gap-1 rounded-lg border border-border bg-surface p-1" role="radiogroup" aria-label="Model">
            {MODES.map((m) => (
              <button
                key={m.value}
                role="radio"
                aria-checked={mode === m.value}
                onClick={() => setMode(m.value)}
                className={cn(
                  "rounded-md px-3 py-1 text-sm transition",
                  mode === m.value ? "bg-surface-2 font-medium text-foreground" : "text-muted hover:text-foreground",
                )}
              >
                {m.label}
              </button>
            ))}
          </div>
        }
      />

      <div className="flex-1 space-y-4 overflow-y-auto rounded-xl border border-border bg-surface p-4 sm:p-6">
        {messages.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center text-center text-sm text-subtle">
            <p>Ask anything. In Auto mode, simple questions go to a fast model and coding or hard questions to a stronger one.</p>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={cn("flex", m.role === "user" ? "justify-end" : "justify-start")}>
            <div
              className={cn(
                "max-w-[85%] rounded-xl px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap",
                m.role === "user" ? "bg-accent text-accent-fg" : "bg-surface-2 text-foreground",
              )}
            >
              {m.content || (busy && i === messages.length - 1 ? <span className="text-subtle">Thinking…</span> : null)}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      <div className="mt-3 flex min-h-6 flex-wrap items-center gap-2 text-xs text-muted">
        {meta && (
          <>
            {meta.tier && <Badge>tier: {meta.tier}</Badge>}
            {meta.model && <Badge>model: {meta.model}</Badge>}
            {meta.cache === "HIT" && <Badge tone="accent">from cache</Badge>}
          </>
        )}
        <ErrorText>{error}</ErrorText>
      </div>

      <form onSubmit={send} className="mt-2 flex items-end gap-2">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          rows={2}
          placeholder="Message the gateway… (Enter to send, Shift+Enter for a new line)"
          className="min-h-[2.75rem] flex-1 resize-none rounded-lg border border-border bg-surface px-3 py-2.5 text-sm placeholder:text-subtle focus:border-accent focus:ring-2 focus:ring-accent/25 focus:outline-none"
        />
        {busy ? (
          <Button type="button" variant="secondary" onClick={() => abortRef.current?.abort()}>
            Stop
          </Button>
        ) : (
          <Button type="submit" disabled={!input.trim()}>
            Send
          </Button>
        )}
        {messages.length > 0 && !busy && (
          <Button type="button" variant="ghost" onClick={() => setMessages([])}>
            Clear
          </Button>
        )}
      </form>
    </div>
  );
}
