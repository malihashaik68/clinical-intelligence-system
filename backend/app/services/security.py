"""Password hashing and API tokens using only the standard library.

Passwords: PBKDF2-HMAC-SHA256 with a random salt.
Tokens: "<practitioner_id>.<expiry>.<hmac signature>", signed with APP_SECRET_KEY.
"""
import base64
import hashlib
import hmac
import os
import secrets
import time

_ITERATIONS = 200_000
SECRET_KEY = os.getenv("APP_SECRET_KEY") or secrets.token_hex(32)  # set it in production
TOKEN_TTL_SECONDS = 8 * 3600


def hash_secret(value: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", value.encode(), salt, _ITERATIONS)
    return f"pbkdf2${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_secret(value: str, stored: str) -> bool:
    try:
        _, salt_b64, digest_b64 = stored.split("$")
        salt, expected = base64.b64decode(salt_b64), base64.b64decode(digest_b64)
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", value.encode(), salt, _ITERATIONS)
    return hmac.compare_digest(digest, expected)


def _sign(payload: str) -> str:
    return hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()


def create_token(practitioner_id: int, ttl: int = TOKEN_TTL_SECONDS) -> str:
    payload = f"{practitioner_id}.{int(time.time()) + ttl}"
    return f"{payload}.{_sign(payload)}"


def read_token(token: str) -> int | None:
    """Return the practitioner id if the token is valid and not expired."""
    try:
        pid, expiry, signature = token.split(".")
    except (ValueError, AttributeError):
        return None
    if not hmac.compare_digest(signature, _sign(f"{pid}.{expiry}")) or int(expiry) < time.time():
        return None
    return int(pid)
