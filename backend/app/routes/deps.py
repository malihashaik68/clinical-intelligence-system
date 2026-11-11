from fastapi import Header, HTTPException

from backend.app.services.patient_service import User, get_user
from backend.app.services.security import read_token


def current_user(authorization: str = Header(default="")) -> User:
    """Require 'Authorization: Bearer <token>' from POST /auth/login."""
    token = authorization.removeprefix("Bearer ").strip()
    pid = read_token(token) if token else None
    user = get_user(pid) if pid else None
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    return user
