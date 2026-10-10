from app.config import settings


async def test_register_login_logout(client, user):
    assert (await client.get("/auth/me")).json()["email"] == user["email"]

    assert (await client.post("/auth/logout")).status_code == 200
    assert (await client.get("/auth/me")).status_code == 401

    r = await client.post("/auth/login", json={"email": user["email"], "password": user["password"]})
    assert r.status_code == 200
    assert (await client.get("/auth/me")).status_code == 200


async def test_session_cookie_is_httponly(client):
    r = await client.post("/auth/register", json={"email": "cookie@example.com", "password": "password123"})
    cookie = r.headers["set-cookie"].lower()
    assert "llmgw_session=" in cookie
    assert "httponly" in cookie
    assert "samesite=lax" in cookie


async def test_duplicate_email_rejected(client, user):
    r = await client.post("/auth/register", json={"email": user["email"].upper(), "password": "password123"})
    assert r.status_code == 409


async def test_validation(client):
    assert (await client.post("/auth/register", json={"email": "not-an-email", "password": "password123"})).status_code == 422
    assert (await client.post("/auth/register", json={"email": "a@b.co", "password": "short"})).status_code == 422


async def test_wrong_password_and_lockout(client, user):
    creds = {"email": user["email"], "password": "wrong-password"}
    for _ in range(settings.login_max_attempts):
        assert (await client.post("/auth/login", json=creds)).status_code == 401
    # Locked out now, even with the right password.
    r = await client.post("/auth/login", json={"email": user["email"], "password": user["password"]})
    assert r.status_code == 429


async def test_dashboard_requires_login(client):
    for path in ("/api/keys", "/api/usage", "/api/providers"):
        assert (await client.get(path)).status_code == 401
