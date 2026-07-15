from __future__ import annotations
from fastapi import Header, HTTPException
from server.services.auth_service import decode_jwt

def get_current_user(authorization: str = Header(default="")) -> dict:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        return decode_jwt(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

def require_admin(user: dict) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return user
