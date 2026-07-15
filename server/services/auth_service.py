from __future__ import annotations

import base64
import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

import jwt
from passlib.hash import argon2

from server.config.settings import (
    JWT_SECRET, JWT_ISSUER, JWT_TTL_SECONDS,
    MAX_FAILED_ATTEMPTS, LOCKOUT_SECONDS
)
from server.config.settings import OTP_ECHO_TO_CLIENT
from server.db.mongo import get_db
from server.services.audit_service import log_event
from server.services.otp_service import create_otp, pop_and_verify, get_nonce
from server.services.crypto_pki import verify_nonce_signature, is_revoked

_runtime_jwt_secret: str | None = None

def _now():
    return datetime.now(timezone.utc)

def _jwt_secret() -> str:
    global _runtime_jwt_secret
    if JWT_SECRET:
        return JWT_SECRET
    if _runtime_jwt_secret is None:
        _runtime_jwt_secret = base64.urlsafe_b64encode(os.urandom(32)).decode("utf-8")
    return _runtime_jwt_secret

def hash_password(password: str) -> str:
    return argon2.hash(password)

def verify_password(password: str, hashed: str) -> bool:
    try:
        return argon2.verify(password, hashed)
    except Exception:
        return False

def get_user(username: str) -> Optional[dict]:
    db = get_db()
    return db.users.find_one({"username": username})

def set_lock(username: str, seconds: int):
    db = get_db()
    db.users.update_one({"username": username}, {"$set": {"locked_until": _now() + timedelta(seconds=seconds)}})

def is_locked(user: dict) -> bool:
    until = user.get("locked_until")
    if not until:
        return False
    return _now() < until

def record_failed_login(username: str):
    db = get_db()
    user = get_user(username)
    if not user:
        return
    failed = int(user.get("failed_attempts", 0)) + 1
    update = {"$set": {"failed_attempts": failed}}
    db.users.update_one({"username": username}, update)
    if failed >= MAX_FAILED_ATTEMPTS:
        set_lock(username, LOCKOUT_SECONDS)
        db.users.update_one({"username": username}, {"$set": {"failed_attempts": 0}})
        log_event("ACCOUNT_LOCKED", username, username, "Account locked due to repeated failures", {"lock_seconds": LOCKOUT_SECONDS}, severity="WARN")

def reset_failed(username: str):
    db = get_db()
    db.users.update_one({"username": username}, {"$set": {"failed_attempts": 0}})

def request_otp_challenge(username: str, password: str) -> dict:
    user = get_user(username)
    if not user:
        raise ValueError("Invalid credentials")
    if is_locked(user):
        raise ValueError("Account is locked. Try again in 2 minutes.")
    if not verify_password(password, user.get("password_hash","")):
        record_failed_login(username)
        log_event("LOGIN_FAILED", username, username, "Wrong password", {}, severity="WARN")
        raise ValueError("Invalid credentials")
    # success password
    otp_token, otp_code, nonce = create_otp(username)
    print(f"[PramaanHR OTP] user={username} otp={otp_code} (valid 2 min)")
    log_event("OTP_ISSUED", username, username, "OTP issued", {})
    resp = {"otp_token": otp_token, "nonce": nonce, "message": "OTP issued."}
    # Local demo convenience: allow the client UI to show the OTP in a popup.
    # Disable by setting OTP_ECHO_TO_CLIENT=false.
    if OTP_ECHO_TO_CLIENT:
        resp["otp_code"] = otp_code
    return resp

def verify_login(otp_token: str, otp_code: str, signature_b64: str) -> dict:
    rec = pop_and_verify(otp_token, otp_code)
    if not rec:
        raise ValueError("OTP invalid or expired.")
    username = rec.username
    nonce = rec.nonce
    user = get_user(username)
    if not user:
        raise ValueError("Invalid login.")
    if is_locked(user):
        raise ValueError("Account is locked. Try again in 2 minutes.")
    cert_pem = user.get("cert_pem")
    serial = user.get("cert_serial")
    if not cert_pem or not serial:
        raise ValueError("No certificate enrolled for this account.")
    if is_revoked(str(serial)):
        log_event("LOGIN_BLOCKED_REVOKED", username, username, "Certificate revoked", {"serial": str(serial)}, severity="WARN")
        raise ValueError("Certificate revoked. Contact admin.")
    if not verify_nonce_signature(nonce, signature_b64, cert_pem):
        record_failed_login(username)
        log_event("LOGIN_FAILED", username, username, "Certificate challenge failed", {}, severity="WARN")
        raise ValueError("Certificate verification failed.")
    reset_failed(username)
    token = issue_jwt(username, user.get("role","employee"))
    log_event("LOGIN_SUCCESS", username, username, "Login successful", {})
    return {"access_token": token, "role": user.get("role","employee")}

def issue_jwt(username: str, role: str) -> str:
    payload = {
        "iss": JWT_ISSUER,
        "sub": username,
        "role": role,
        "iat": int(_now().timestamp()),
        "exp": int((_now() + timedelta(seconds=JWT_TTL_SECONDS)).timestamp()),
    }
    return jwt.encode(payload, _jwt_secret(), algorithm="HS256")

def decode_jwt(token: str) -> dict:
    return jwt.decode(token, _jwt_secret(), algorithms=["HS256"], issuer=JWT_ISSUER)

def require_role(payload: dict, roles: set[str]):
    if payload.get("role") not in roles:
        raise PermissionError("Insufficient privileges.")
