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
  daily: { date: string; requests: number; cost_usd: number }[];
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

export type Providers = Record<"cheap" | "strong", { name: string; provider: string; model: string }[]>;

export interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
}
