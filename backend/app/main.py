import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app import clients
from app.config import settings
from app.db import engine
from app.middleware import RequestContextMiddleware, configure_logging, request_id_var
from app.routers import auth, gateway, keys
from app.services.accounting import drain
from app.services.llm import TIERS, chain_for

configure_logging(settings.log_level, json_logs=settings.is_production)
log = logging.getLogger("app")

DOCS = """
**How to test here**

1. `POST /auth/register` (or `/auth/login`). The browser keeps the session cookie, so the `/api/*` endpoints then work.
2. `POST /api/keys` returns your `sk-mysite-...` key. It is shown only once.
3. Click **Authorize** (top right), paste the key, then try `POST /v1/chat/completions`.

`model` can be `auto` (gateway picks), `cheap` or `strong`. Use `"stream": false` here, because Swagger doesn't render streams.
"""


@asynccontextmanager
async def lifespan(_app: FastAPI):
    log.info("provider chains: %s", {t: [d.name for d in chain_for(t)] for t in TIERS})
    yield
    await drain()
    await clients.redis.aclose()
    await engine.dispose()


app = FastAPI(title="LLM API Gateway", description=DOCS, version="1.0.0", lifespan=lifespan)

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
app.add_middleware(RequestContextMiddleware)

app.include_router(auth.router)
app.include_router(keys.router)
app.include_router(gateway.router)


@app.exception_handler(Exception)
async def unhandled(_request: Request, exc: Exception):
    log.exception("unhandled error", exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error", "request_id": request_id_var.get()})


@app.get("/", include_in_schema=False)
async def root():
    return {"name": "LLM API Gateway", "docs": "/docs"}


@app.get("/health", tags=["ops"])
async def health():
    """Liveness: the process is up."""
    return {"status": "ok"}


@app.get("/ready", tags=["ops"])
async def ready():
    """Readiness: database and Redis reachable, and which providers are configured."""
    checks = {}
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:  # noqa: BLE001
        checks["database"] = f"error: {type(e).__name__}"
    try:
        await clients.redis.ping()
        checks["redis"] = "ok"
    except Exception as e:  # noqa: BLE001
        checks["redis"] = f"error: {type(e).__name__}"
    checks["providers"] = {t: [d.name for d in chain_for(t)] for t in TIERS}
    healthy = checks["database"] == "ok" and checks["redis"] == "ok"
    return JSONResponse(status_code=200 if healthy else 503, content={"status": "ok" if healthy else "degraded", **checks})
