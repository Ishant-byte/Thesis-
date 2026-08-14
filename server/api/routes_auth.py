from __future__ import annotations

import base64
import logging
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Literal

from server.db.mongo import get_db
from server.services.auth_service import (
    hash_activation_token,
    hash_password,
    request_otp_challenge,
    verify_login,
)
from server.services.validation import (
    validate_username,
    validate_password,
)
from server.services.crypto_pki import issue_user_certificate
from server.services.audit_service import log_event

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)


def _now():
    return datetime.now(timezone.utc)


def _activation_invalid_or_expired() -> HTTPException:
    return HTTPException(status_code=400, detail="Activation token is invalid or expired.")


def _clear_activation_claim(db, username: str, token_hash: str) -> None:
    db.users.update_one(
        {"username": username, "activation.token_hash": token_hash},
        {"$set": {"activation.claimed_at": None}},
    )


class OTPRequest(BaseModel):
    username: str
    password: str
    portal: Literal["employee", "admin"]


class OTPVerify(BaseModel):
    otp_token: str
    otp_code: str
    signature_b64: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    first_name: str
    last_name: str
    job_role: str
    department: str
    phone: str | None = None
    role: str = "employee"


class ActivateRequest(BaseModel):
    token: str
    password: str


@router.post("/request-otp")
def request_otp(body: OTPRequest):
    """Password check + OTP issuance.

    Returns otp_token + nonce. In demo mode, the OTP may also be returned to the
    browser so the web UI can show it during a local demonstration.
    """
    try:
        validate_username(body.username)
        if not body.password:
            raise ValueError("Password is required")
        return request_otp_challenge(body.username, body.password, body.portal)
    except ValueError as e:
        msg = str(e)
        if msg == "Invalid credentials":
            raise HTTPException(status_code=401, detail=msg)
        if msg == "This account is inactive.":
            raise HTTPException(status_code=403, detail=msg)
        if msg == "This account is pending activation.":
            raise HTTPException(status_code=403, detail=msg)
        if msg.startswith("Account is locked"):
            raise HTTPException(status_code=423, detail=msg)
        if msg == "This account is not authorized for the selected portal.":
            raise HTTPException(status_code=403, detail=msg)
        raise HTTPException(status_code=400, detail=msg)


@router.post("/verify")
def verify(body: OTPVerify):
    """OTP verify + cert challenge-response (client signs nonce)."""
    try:
        return verify_login(body.otp_token, body.otp_code, body.signature_b64)
    except ValueError as e:
        msg = str(e)
        if msg.startswith("OTP invalid"):
            raise HTTPException(status_code=401, detail=msg)
        if msg == "This account is inactive.":
            raise HTTPException(status_code=403, detail=msg)
        if msg.startswith("Certificate revoked"):
            raise HTTPException(status_code=403, detail=msg)
        if msg.startswith("Account is locked"):
            raise HTTPException(status_code=423, detail=msg)
        raise HTTPException(status_code=400, detail=msg)


@router.post("/register")
def register(body: RegisterRequest):
    raise HTTPException(status_code=403, detail="Self-registration is disabled. Contact an administrator for an activation link.")


@router.post("/activate")
def activate_account(body: ActivateRequest):
    db = get_db()
    token = (body.token or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="Activation token is required.")
    try:
        validate_password(body.password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    token_hash = hash_activation_token(token)
    user = db.users.find_one({"activation.token_hash": token_hash})
    if not user:
        raise _activation_invalid_or_expired()

    activation = user.get("activation") or {}
    expires_at = activation.get("expires_at")
    if user.get("active", True) or not activation.get("token_hash") or expires_at is None:
        raise _activation_invalid_or_expired()
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= _now():
        raise _activation_invalid_or_expired()

    claim = db.users.update_one(
        {"username": user["username"], "active": False, "activation.token_hash": token_hash, "activation.claimed_at": None},
        {"$set": {"activation.claimed_at": _now()}},
    )
    if getattr(claim, "matched_count", 1) != 1:
        raise HTTPException(status_code=400, detail="Activation token is invalid or already used.")

    try:
        cert_info = issue_user_certificate(user["username"], body.password, actor_admin=None)
        finish = db.users.update_one(
            {"username": user["username"], "activation.token_hash": token_hash},
            {
                "$set": {
                    "password_hash": hash_password(body.password),
                    "active": True,
                    "cert_pem": cert_info["cert_pem"],
                    "cert_serial": str(cert_info["serial"]),
                    "public_key_pem": cert_info["public_key_pem"],
                    "pkcs12_path": cert_info["pkcs12_path"],
                    "presence_state": "offline",
                    "last_seen": _now(),
                },
                "$unset": {"activation": ""},
            },
        )
        if getattr(finish, "matched_count", 1) != 1:
            raise HTTPException(status_code=400, detail="Activation token is invalid or already used.")
    except HTTPException:
        _clear_activation_claim(db, user["username"], token_hash)
        raise
    except Exception:
        _clear_activation_claim(db, user["username"], token_hash)
        logger.exception("Activation certificate issuance failed for username=%s", user["username"])
        raise HTTPException(status_code=503, detail="Activation failed. Contact an administrator for a new activation link.")

    log_event(
        "USER_ACTIVATED",
        user["username"],
        user["username"],
        "Pending account activated",
        {"role": user.get("role", "employee"), "serial": str(cert_info["serial"])},
    )
    return {
        "ok": True,
        "username": user["username"],
        "role": user.get("role", "employee"),
        "message": "Activation successful. Download and securely store your keystore.",
        "keystore_b64": base64.b64encode(Path(cert_info["pkcs12_path"]).read_bytes()).decode("ascii"),
        "keystore_filename": f"{user['username']}-keystore.p12",
    }
