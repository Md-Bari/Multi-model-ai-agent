from sqlalchemy import select

from app.db import SessionLocal
from app.models import ApiKey
from app.security import hash_api_key


async def test_key_is_shown_once_and_stored_hashed(client, user):
    r = await client.post("/api/keys", json={"name": "app", "rpm_limit": 10, "budget_usd": 2, "expires_days": 30})
    assert r.status_code == 201
    created = r.json()
    raw = created["key"]
    assert raw.startswith("sk-mysite-")
    assert created["prefix"] == raw[:14] + "..."

    listed = (await client.get("/api/keys")).json()
    assert len(listed) == 1
    assert "key" not in listed[0]

    async with SessionLocal() as db:
        row = await db.scalar(select(ApiKey).where(ApiKey.id == created["id"]))
    assert row.key_hash == hash_api_key(raw)
    assert raw not in (row.key_hash, row.prefix)


async def test_revoke(client, user, api_key, providers):
    key_id = (await client.get("/api/keys")).json()[0]["id"]
    headers = {"Authorization": f"Bearer {api_key}"}
    assert (await client.get("/v1/models", headers=headers)).status_code == 200

    assert (await client.delete(f"/api/keys/{key_id}")).status_code == 200
    r = await client.get("/v1/models", headers=headers)
    assert r.status_code == 401
    assert r.json()["detail"] == "API key revoked"


async def test_cannot_revoke_someone_elses_key(client, user, api_key):
    key_id = (await client.get("/api/keys")).json()[0]["id"]
    await client.post("/auth/logout")
    await client.post("/auth/register", json={"email": "other@example.com", "password": "password123"})
    assert (await client.delete(f"/api/keys/{key_id}")).status_code == 404
