import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

import auth
import gateway
import keys
from db import init_db
from llm import CHAINS
from security import redis

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

STATIC = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await init_db()
    logging.getLogger("gateway").info("provider chains: %s", CHAINS)
    yield
    await redis.aclose()


DOCS = """
**How to test here**

1. `POST /auth/register` (or `/auth/login`). The browser keeps the session cookie, so the `/api/*` endpoints then work.
2. `POST /api/keys` returns your `sk-mysite-...` key. It is shown only once.
3. Click **Authorize** (top right), paste the key, then try `POST /v1/chat/completions`.

`model` can be `auto` (gateway picks), `cheap` or `strong`. Use `"stream": false` here, because Swagger doesn't render streams.
"""

app = FastAPI(title="LLM API Gateway", description=DOCS, lifespan=lifespan)
app.include_router(auth.router)
app.include_router(keys.router)
app.include_router(gateway.router)


@app.get("/", include_in_schema=False)
async def dashboard():
    return FileResponse(STATIC / "index.html")


@app.get("/health")
async def health():
    await redis.ping()
    return {"status": "healthy", "providers": {tier: chain for tier, chain in CHAINS.items()}}
