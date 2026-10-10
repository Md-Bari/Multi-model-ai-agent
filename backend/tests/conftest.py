"""Test setup: SQLite instead of Postgres, fakeredis instead of Redis, and fake LangChain
chat models instead of real providers. No network or API keys needed."""

import os
import tempfile
import uuid
from pathlib import Path

_db_file = Path(tempfile.gettempdir()) / f"llmgw-test-{uuid.uuid4().hex}.db"
os.environ.update(
    {
        "ENVIRONMENT": "test",
        "DATABASE_URL": f"sqlite+aiosqlite:///{_db_file.as_posix()}",
        "REDIS_URL": "redis://unused:6379/0",
        "GROQ_API_KEY": "test-groq",
        "GEMINI_API_KEY": "test-gemini",
        "CACHE_TTL_SECONDS": "3600",
    }
)

import fakeredis  # noqa: E402
import httpx  # noqa: E402
import pytest  # noqa: E402
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402

from app import clients, models  # noqa: E402, F401
from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services import accounting, llm  # noqa: E402

clients.redis = fakeredis.FakeAsyncRedis(decode_responses=True)


class BrokenModel(GenericFakeChatModel):
    async def _astream(self, *args, **kwargs):
        raise RuntimeError("provider down")
        yield  # pragma: no cover - makes this an async generator


class FakeProviders:
    """Controls what each deployment does: reply with text, or fail."""

    def __init__(self):
        self.broken: set[str] = set()
        self.calls: list[str] = []

    def build(self, dep, temperature, max_tokens):
        self.calls.append(dep.name)
        if dep.name in self.broken:
            return BrokenModel(messages=iter([]))
        return GenericFakeChatModel(messages=iter([AIMessage(content=f"answer from {dep.name}")]))


@pytest.fixture(scope="session", autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()
    _db_file.unlink(missing_ok=True)


@pytest.fixture(autouse=True)
async def _clean_redis():
    await clients.redis.flushall()
    yield


@pytest.fixture
def providers(monkeypatch) -> FakeProviders:
    fake = FakeProviders()
    monkeypatch.setattr(llm, "build_chat_model", fake.build)
    return fake


@pytest.fixture
async def client():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
async def user(client):
    """A registered, logged-in user (session cookie kept on `client`)."""
    email = f"u{uuid.uuid4().hex[:10]}@example.com"
    r = await client.post("/auth/register", json={"email": email, "password": "password123"})
    assert r.status_code == 201
    return {"email": email, "password": "password123", **r.json()}


@pytest.fixture
async def api_key(client, user) -> str:
    r = await client.post("/api/keys", json={"name": "test", "rpm_limit": 100})
    assert r.status_code == 201
    return r.json()["key"]


async def settle():
    """Let background accounting tasks finish before asserting on usage."""
    await accounting.drain()
