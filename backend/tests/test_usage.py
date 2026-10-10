from tests.conftest import settle


def ask(text: str) -> dict:
    return {"messages": [{"role": "user", "content": text}]}


async def _traffic(client, api_key, providers):
    headers = {"Authorization": f"Bearer {api_key}"}
    await client.post("/v1/chat/completions", json=ask("first question"), headers=headers)
    await settle()
    await client.post("/v1/chat/completions", json=ask("first question"), headers=headers)  # cache hit
    await client.post("/v1/chat/completions", json=ask("Fix this python bug"), headers=headers)  # strong tier
    await client.post("/api/playground/chat", json=ask("from the playground"))
    providers.broken.update({"groq-fast", "groq-large", "gemini"})
    await client.post("/v1/chat/completions", json=ask("this one fails"), headers=headers)
    await settle()


async def test_timeseries_hourly(client, api_key, providers):
    await _traffic(client, api_key, providers)
    r = await client.get("/api/usage/timeseries", params={"range": "24h", "tz_offset": 360})
    assert r.status_code == 200
    data = r.json()
    assert data["unit"] == "hour"
    assert len(data["buckets"]) == 24
    assert data["buckets"][-1]["t"].endswith(":00")

    totals = data["totals"]
    assert totals["requests"] == 5
    assert totals["cached"] == 1
    assert totals["errors"] == 1
    assert totals["input_tokens"] > 0 and totals["output_tokens"] > 0
    # Everything happened just now, so it all lands in the latest bucket.
    assert data["buckets"][-1]["requests"] == 5
    assert sum(b["requests"] for b in data["by_model"]) == 5
    assert {k["name"] for k in data["by_key"]} == {"test", "Playground"}
    assert "llama-3.1-8b-instant" in data["filters"]["models"]
    assert "none" not in data["filters"]["models"]


async def test_timeseries_daily_and_filters(client, api_key, providers):
    await _traffic(client, api_key, providers)
    data = (await client.get("/api/usage/timeseries", params={"range": "28d"})).json()
    assert data["unit"] == "day"
    assert len(data["buckets"]) == 28

    only_playground = (await client.get("/api/usage/timeseries", params={"range": "7d", "key": "playground"})).json()
    assert only_playground["totals"]["requests"] == 1

    key_id = data["filters"]["keys"][0]["id"]
    only_key = (await client.get("/api/usage/timeseries", params={"range": "7d", "key": str(key_id)})).json()
    assert only_key["totals"]["requests"] == 4

    only_model = (await client.get("/api/usage/timeseries", params={"range": "7d", "model": "gemini-3.8-flash"})).json()
    assert only_model["totals"]["requests"] == 1


async def test_timeseries_validation(client, user):
    assert (await client.get("/api/usage/timeseries", params={"range": "1y"})).status_code == 422
    assert (await client.get("/api/usage/timeseries", params={"tz_offset": 99999})).status_code == 422


async def test_limits_show_current_minute(client, api_key, providers):
    headers = {"Authorization": f"Bearer {api_key}"}
    for _ in range(3):
        await client.get("/v1/models", headers=headers)
    await client.post("/api/playground/chat", json=ask("hi"))
    await settle()

    limits = (await client.get("/api/usage/limits")).json()
    key_entry = next(item for item in limits if item["name"] == "test")
    assert key_entry["requests_this_minute"] == 3
    assert key_entry["rpm_limit"] == 100
    playground = next(item for item in limits if item["key_id"] is None)
    assert playground["requests_this_minute"] == 1
    assert playground["requests_24h"] == 1


async def test_usage_requires_login(client):
    assert (await client.get("/api/usage/timeseries")).status_code == 401
    assert (await client.get("/api/usage/limits")).status_code == 401
