export interface User {
  id: number;
  email: string;
}

export interface ApiKey {
  id: number;
  name: string;
  prefix: string;
  revoked: boolean;
  expires_at: string | null;
  rpm_limit: number;
  budget_usd: number | null;
  spent_usd: number;
  last_used_at: string | null;
  created_at: string;
}

export interface CreatedKey extends ApiKey {
  key: string;
}

export interface Usage {
  totals: {
    requests: number;
    prompt_tokens: number;
    completion_tokens: number;
    cost_usd: number;
    cache_hits: number;
    errors: number;
    avg_latency_ms: number;
  };
  by_model: { model: string; requests: number; tokens: number; cost_usd: number }[];
  recent: {
    id: number;
    created_at: string;
    key_id: number | null;
    tier: string;
    model: string;
    prompt_tokens: number;
    completion_tokens: number;
    cost_usd: number;
    latency_ms: number;
    cached: boolean;
    status: string;
  }[];
}

export interface UsageMetrics {
  requests: number;
  cached: number;
  errors: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  avg_latency_ms: number;
}

export type UsageRange = "24h" | "7d" | "28d" | "90d";

export interface Timeseries {
  range: UsageRange;
  unit: "hour" | "day";
  buckets: (UsageMetrics & { t: string })[];
  totals: Omit<UsageMetrics, "avg_latency_ms">;
  by_model: (UsageMetrics & { model: string })[];
  by_key: (UsageMetrics & { key_id: number | null; name: string })[];
  filters: { models: string[]; keys: { id: number; name: string }[] };
}

export interface KeyLimit {
  key_id: number | null;
  name: string;
  rpm_limit: number;
  requests_this_minute: number;
  requests_24h: number;
  tokens_24h: number;
  budget_usd: number | null;
  spent_usd: number | null;
}

export type Providers =Record<"cheap" | "strong", { name: string; provider: string; model: string }[]>;

export interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
}
