import asyncio
import hashlib
import hmac
import secrets

KEY_PREFIX = "sk-mysite-"
_SCRYPT = {"n": 2**14, "r": 8, "p": 1}


def _scrypt(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)


async def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    # scrypt is deliberately slow; keep it off the event loop.
    digest = await asyncio.to_thread(_scrypt, password, salt)
    return f"scrypt${salt.hex()}${digest.hex()}"


async def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    digest = await asyncio.to_thread(_scrypt, password, bytes.fromhex(salt_hex))
    return hmac.compare_digest(digest.hex(), digest_hex)


def generate_api_key() -> str:
    return KEY_PREFIX + secrets.token_urlsafe(32)


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def display_prefix(raw_key: str) -> str:
    return raw_key[: len(KEY_PREFIX) + 4] + "..."
