import json

from sqlalchemy import update

from app.db import SessionLocal
from app.models import ApiKey
from tests.conftest import settle


def ask(text: str, **extra) -> dict:
    return {"messages": [{"role": "user", "content": text}], **extra}


def sse_text(body: str) -> str:
    out = []
    for line in body.splitlines():
        if line.startswith("data: {"):
            event = json.loads(line[6:])
            for choice in event.get("choices", []):
                out.append(choice["delta"].get("content") or "")
    return "".join(out)


async def test_auth_required(client):
    r = await client.post("/v1/chat/completions", json=ask("hi"))
    assert r.status_code == 401
    r = await client.post("/v1/chat/completions", json=ask("hi"), headers={"Authorization": "Bearer sk-mysite-nope"})
    assert r.status_code == 401


async def test_simple_question_goes_to_cheap_tier(client, api_key, providers):
    r = await client.post(
        "/v1/chat/completions", json=ask("What is the capital of France?"), headers={"Authorization": f"Bearer {api_key}"}
    )
    assert r.status_code == 200
    assert r.headers["x-gateway-tier"] == "cheap"
    assert r.headers["x-gateway-cache"] == "MISS"
    body = r.json()
    assert body["object"] == "chat.completion"
    assert body["choices"][0]["message"]["content"] == "answer from groq-fast"
    assert body["usage"]["total_tokens"] > 0
    assert r.headers["x-request-id"]


async def test_code_question_goes_to_strong_tier(client, api_key, providers):
    r = await client.post(
        "/v1/chat/completions", json=ask("Fix this python bug please"), headers={"Authorization": f"Bearer {api_key}"}
    )
    assert r.headers["x-gateway-tier"] == "strong"
    assert r.json()["choices"][0]["message"]["content"] == "answer from gemini"


async def test_fallback_and_circuit_breaker(client, api_key, providers):
    providers.broken.add("groq-fast")
    headers = {"Authorization": f"Bearer {api_key}"}

    r = await client.post("/v1/chat/completions", json=ask("hello one"), headers=headers)
    assert r.status_code == 200
    assert r.json()["choices"][0]["message"]["content"] == "answer from gemini"
    assert providers.calls == ["groq-fast", "gemini"]

    # groq-fast's circuit is now open, so the next request skips it entirely.
    providers.calls.clear()
    r = await client.post("/v1/chat/completions", json=ask("hello two"), headers=headers)
    assert r.status_code == 200
    assert providers.calls == ["gemini"]


async def test_all_providers_down(client, api_key, providers):
    providers.broken.update({"groq-fast", "groq-large", "gemini"})
    r = await client.post("/v1/chat/completions", json=ask("hi"), headers={"Authorization": f"Bearer {api_key}"})
    assert r.status_code == 502


async def test_cache_hit_on_normalized_prompt(client, api_key, providers):
    headers = {"Authorization": f"Bearer {api_key}"}
    await client.post("/v1/chat/completions", json=ask("What is 2+2?"), headers=headers)
    await settle()
    providers.calls.clear()

    r = await client.post("/v1/chat/completions", json=ask("  what IS 2+2?  "), headers=headers)
    assert r.headers["x-gateway-cache"] == "HIT"
    assert r.json()["choices"][0]["message"]["content"] == "answer from groq-fast"
    assert providers.calls == []


async def test_streaming(client, api_key, providers):
    r = await client.post(
        "/v1/chat/completions", json=ask("Stream me", stream=True), headers={"Authorization": f"Bearer {api_key}"}
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    assert sse_text(r.text) == "answer from groq-fast"
    assert r.text.strip().endswith("data: [DONE]")


async def test_unknown_model(client, api_key, providers):
    r = await client.post("/v1/chat/completions", json=ask("hi", model="gpt-4"), headers={"Authorization": f"Bearer {api_key}"})
    assert r.status_code == 400


async def test_rate_limit(client, user, providers):
    key = (await client.post("/api/keys", json={"name": "slow", "rpm_limit": 2})).json()["key"]
    headers = {"Authorization": f"Bearer {key}"}
    codes = [(await client.get("/v1/models", headers=headers)).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


async def test_budget_exhausted(client, user, providers):
    created = (await client.post("/api/keys", json={"name": "capped", "budget_usd": 1})).json()
    async with SessionLocal() as db:
        await db.execute(update(ApiKey).where(ApiKey.id == created["id"]).values(spent_usd=1.5))
        await db.commit()
    r = await client.post("/v1/chat/completions", json=ask("hi"), headers={"Authorization": f"Bearer {created['key']}"})
    assert r.status_code == 402


async def test_usage_is_recorded(client, api_key, providers):
    headers = {"Authorization": f"Bearer {api_key}"}
    await client.post("/v1/chat/completions", json=ask("count me"), headers=headers)
    await settle()
    await client.post("/v1/chat/completions", json=ask("count me"), headers=headers)  # cache hit
    await settle()

    usage = (await client.get("/api/usage")).json()
    assert usage["totals"]["requests"] == 2
    assert usage["totals"]["cache_hits"] == 1
    assert usage["recent"][0]["cached"] is True
    assert usage["by_model"][0]["model"] == "llama-3.1-8b-instant"


async def test_playground_uses_session(client, user, providers):
    r = await client.post("/api/playground/chat", json=ask("hi from playground"))
    assert r.status_code == 200
    assert r.json()["choices"][0]["message"]["content"] == "answer from groq-fast"
    await settle()
    recent = (await client.get("/api/usage")).json()["recent"]
    assert recent[0]["key_id"] is None
