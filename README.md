# LLM Gateway

One OpenAI-compatible API in front of **Gemini** and **Groq**. Users sign up, create their own `sk-mysite-...` keys, and call the gateway; the gateway verifies the key, picks a model, serves from cache when it can, falls back between providers, and records tokens and cost.

```
App (Bearer sk-mysite-...)
  │
  ▼
FastAPI ── verify key hash · rate limit · budget ──────────────► Redis
  │
  ▼
Router ── simple → fast tier · coding / hard → strong tier
  │
  ▼
Cache ── hit? → answer instantly, $0 ──────────────────────────► Redis
  │ miss
  ▼
LangChain ── Groq / Gemini, automatic fallback + circuit breaker
  │
  ▼
Stream back (SSE) + cache ── log tokens / cost / latency ──────► PostgreSQL
```

| Part | Stack |
|---|---|
| Backend | FastAPI, LangChain (`langchain-groq`, `langchain-google-genai`), SQLAlchemy 2 async, Alembic, Redis |
| Frontend | Next.js 16 (App Router, Cache Components), Tailwind CSS 4, TypeScript |
| Free hosting | Render (API) · Neon (Postgres) · Upstash (Redis) · Vercel (frontend) · GitHub Actions (CI) |

## Features

- **OpenAI-compatible** `POST /v1/chat/completions` (streaming and non-streaming) and `GET /v1/models`. The OpenAI SDKs and LangChain's `ChatOpenAI` work by changing `base_url`.
- **Routing:** `model: "auto"` sends simple prompts to the fast tier and coding or reasoning prompts to the strong tier. `cheap` and `strong` force a tier.
- **Fallback with a circuit breaker:** if a provider errors or is overloaded, the next one in the tier answers, and the failed one is skipped for 30 seconds.
- **Cache:** identical prompts (ignoring case and whitespace) are answered from Redis at zero cost.
- **Per-key controls:** requests per minute, USD budget, expiry date, instant revoke. Only the SHA-256 hash of each key is stored.
- **Dashboard:** usage overview, key management, a streaming playground, and API docs.
- **Operations:** versioned migrations, request IDs on every response, JSON logs in production, `/health` and `/ready` checks, security headers, login brute-force lockout.

## Run locally

Requirements: Docker Desktop. For working outside Docker you also need Python 3.12+ and Node 20.9+.

```bash
cp .env.example .env          # add GEMINI_API_KEY and/or GROQ_API_KEY, set POSTGRES_PASSWORD
docker compose up --build
```

- Frontend: http://localhost:3001
- API docs (Swagger): http://localhost:8000/docs

Only one provider key is required; every tier then uses that provider.

### Without Docker (hot reload)

```bash
docker compose up -d postgres redis

# backend
cd backend
python -m venv .venv && .venv/Scripts/activate      # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload

# frontend (new terminal)
cd frontend
npm install
npm run dev -- --port 3001
```

### Tests and checks

```bash
cd backend  && ruff check . && ruff format --check . && pytest -q
cd frontend && npm run lint && npm run typecheck && npm run build
```

The backend tests use SQLite, fakeredis and fake LangChain models, so they need no network access or API keys. CI also runs the migrations against a real Postgres.

## Deploy for free

You need accounts on Neon, Upstash, Render and Vercel. All four have free plans that need no card.

### 1. Database: Neon

1. Create a project at https://neon.tech. Pick the region closest to your Render region, for example AWS Singapore.
2. Copy the connection string (`postgresql://...neon.tech/neondb?sslmode=require`). The gateway converts it for asyncpg automatically, and pooled (`-pooler`) URLs work too.

### 2. Redis: Upstash

1. Create a Redis database at https://upstash.com in the same region.
2. Copy the **TLS** URL: `rediss://default:<password>@<host>.upstash.io:6379`.

### 3. Backend: Render

1. Go to https://render.com, click **New → Blueprint**, and pick this repository. Render reads [`render.yaml`](render.yaml).
2. Fill the secret values: `DATABASE_URL` (Neon), `REDIS_URL` (Upstash), `GEMINI_API_KEY`, `GROQ_API_KEY`.
3. Deploy. Migrations run automatically on start. Check `https://<service>.onrender.com/ready`.

### 4. Frontend: Vercel

1. Go to https://vercel.com, click **Add New → Project**, import this repository, and set **Root Directory** to `frontend`.
2. Add these environment variables, then deploy:
   - `BACKEND_URL` = `https://<service>.onrender.com`
   - `NEXT_PUBLIC_API_URL` = `https://<service>.onrender.com`

The browser only ever talks to Vercel: `/api/backend/*` is proxied to Render, so the login cookie stays first-party.

### 5. Keep the backend awake (optional)

Render's free plan sleeps after 15 idle minutes, and the next request then takes about 50 seconds. In GitHub, go to **Settings → Secrets and variables → Actions → Variables** and add `BACKEND_URL` = `https://<service>.onrender.com`. The [keep-alive workflow](.github/workflows/keepalive.yml) then pings `/health` every 10 minutes, which stays within Render's 750 free hours a month for one service.

### Free-plan limits to know

| Service | Limit |
|---|---|
| Render | Sleeps when idle (see step 5); 512 MB RAM |
| Neon | 0.5 GB storage; compute pauses when idle and wakes in about 1 second |
| Upstash | 256 MB; 500k commands a month |
| Vercel Hobby | Non-commercial use |
| Gemini / Groq free tiers | Per-minute and per-day request limits; the gateway falls back when one is rate limited |

## Configuration

All settings are environment variables. See [`.env.example`](.env.example) for the full list.

| Variable | Default | Purpose |
|---|---|---|
| `GEMINI_API_KEY`, `GROQ_API_KEY` | – | Provider keys; a provider is used only if its key is set |
| `GEMINI_MODEL` | `gemini-3.8-flash` | Gemini model |
| `GROQ_FAST_MODEL` / `GROQ_LARGE_MODEL` | `llama-3.1-8b-instant` / `openai/gpt-oss-120b` | Groq models |
| `TIER_CHEAP` / `TIER_STRONG` | `groq-fast,gemini` / `gemini,groq-large` | Order per tier: primary, then fallbacks |
| `MODEL_PRICES` | built-in table | USD per 1M tokens, `{"model": [input, output]}` |
| `DATABASE_URL`, `REDIS_URL` | local compose | Connection strings |
| `ENVIRONMENT` | `development` | `production` turns on JSON logs |
| `COOKIE_SECURE` | `false` | Must be `true` behind HTTPS |
| `CACHE_TTL_SECONDS` | `86400` | `0` disables the response cache |

Prices in the built-in table are estimates. Check them against the providers' pricing pages and override them with `MODEL_PRICES`.

## Using the API

```python
from openai import OpenAI

client = OpenAI(base_url="https://<service>.onrender.com/v1", api_key="sk-mysite-...")
reply = client.chat.completions.create(model="auto", messages=[{"role": "user", "content": "Hello!"}])
print(reply.choices[0].message.content)
```

Each response includes `X-Gateway-Tier`, `X-Gateway-Model`, `X-Gateway-Cache` and `X-Request-ID` headers.

| Status | Meaning |
|---|---|
| 401 | Missing, invalid, revoked or expired key |
| 402 | Key budget used up |
| 429 | Rate limit exceeded (`Retry-After` header) |
| 502 | Every provider failed |
| 503 | No provider configured |

**Keep gateway keys on your server.** Anyone who has a key can use it, so never put one in browser code, a public repository or a screenshot.

## Project layout

```
backend/
  app/
    main.py            app setup, middleware, health checks
    config.py          settings (env vars)
    models.py, db.py   database models and engine
    routers/           auth, dashboard (keys, usage, playground), /v1 gateway
    services/          llm (LangChain, routing, fallback), chat pipeline, cache,
                       rate limits, accounting, pricing
  alembic/             migrations
  tests/
frontend/
  src/app/             pages: landing, login/register, dashboard, keys, playground, docs
  src/components/      UI building blocks, chart, app shell
  src/lib/             API client, streaming, formatting
  src/proxy.ts         redirects signed-out users away from app pages
render.yaml            Render blueprint
docker-compose.yml     local stack
```
