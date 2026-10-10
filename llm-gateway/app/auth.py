"""Dashboard login: email + password, session token stored in Redis and sent as a cookie."""

import secrets

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from config import settings
from db import DB, User, get_db
from security import hash_password, redis, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

# Browsers share cookies across all ports of "localhost", so use a name other apps won't reuse.
SESSION_COOKIE = "llmgw_session"


class Credentials(BaseModel):
    model_config = {"json_schema_extra": {"examples": [{"email": "me@example.com", "password": "password123"}]}}

    email: str = Field(min_length=3, max_length=255, pattern=r"^[^@\s]+@[^@\s]+$")
    password: str = Field(min_length=8, max_length=200)


async def current_user(
    session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    db: DB = Depends(get_db),
) -> User:
    if not session:
        raise HTTPException(401, "Not logged in")
    user_id = await redis.get(f"session:{session}")
    if not user_id:
        raise HTTPException(401, "Session expired")
    user = await db.get(User, int(user_id))
    if not user or not user.is_active:
        raise HTTPException(401, "Account disabled")
    return user


async def _start_session(response: Response, user: User) -> None:
    token = secrets.token_urlsafe(32)
    await redis.set(f"session:{token}", user.id, ex=settings.session_ttl_seconds)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
    )


@router.post("/register")
async def register(body: Credentials, response: Response, db: DB = Depends(get_db)):
    email = body.email.lower()
    if await db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "Email already registered")
    user = User(email=email, password_hash=hash_password(body.password))
    db.add(user)
    await db.commit()
    await _start_session(response, user)
    return {"id": user.id, "email": user.email}


@router.post("/login")
async def login(body: Credentials, response: Response, db: DB = Depends(get_db)):
    user = await db.scalar(select(User).where(User.email == body.email.lower()))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Wrong email or password")
    if not user.is_active:
        raise HTTPException(403, "Account disabled")
    await _start_session(response, user)
    return {"id": user.id, "email": user.email}


@router.post("/logout")
async def logout(response: Response, session: str | None = Cookie(default=None, alias=SESSION_COOKIE)):
    if session:
        await redis.delete(f"session:{session}")
    response.delete_cookie(SESSION_COOKIE)
    return {"ok": True}


@router.get("/me")
async def me(user: User = Depends(current_user)):
    return {"id": user.id, "email": user.email}
