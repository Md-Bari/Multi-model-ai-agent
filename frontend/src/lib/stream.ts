import { API_BASE, ApiError } from "./api";
import type { ChatMessage } from "./types";

export interface StreamMeta {
  tier: string | null;
  model: string | null;
  cache: string | null;
}

/**
 * Calls the playground endpoint with stream=true and yields text deltas from the
 * OpenAI-style server-sent events.
 */
export async function* streamChat(
  body: { model: string; messages: ChatMessage[] },
  signal: AbortSignal,
  onMeta: (meta: StreamMeta) => void,
): AsyncGenerator<string> {
  const res = await fetch(`${API_BASE}/api/playground/chat`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...body, stream: true }),
    signal,
  });
  if (!res.ok || !res.body) {
    const data = await res.json().catch(() => null);
    throw new ApiError(res.status, (data && typeof data.detail === "string" && data.detail) || "Request failed");
  }
  onMeta({
    tier: res.headers.get("x-gateway-tier"),
    model: res.headers.get("x-gateway-model"),
    cache: res.headers.get("x-gateway-cache"),
  });

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    const events = buffer.split("\n\n");
    buffer = events.pop() ?? "";
    for (const event of events) {
      const line = event.trim();
      if (!line.startsWith("data: ")) continue;
      const payload = line.slice(6);
      if (payload === "[DONE]") return;
      const data = JSON.parse(payload);
      if (data.error) throw new ApiError(502, data.error.message ?? "Upstream error");
      const delta: string | undefined = data.choices?.[0]?.delta?.content;
      if (delta) yield delta;
    }
  }
}
