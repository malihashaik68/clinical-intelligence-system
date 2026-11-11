from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.app.routes.deps import current_user
from backend.app.services.patient_service import User, authenticate
from backend.app.services.security import create_token

router = APIRouter(prefix="/auth", tags=["Auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(payload: LoginRequest):
    user = authenticate(payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return {"token": create_token(user.id), "user": user.__dict__}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return user.__dict__
