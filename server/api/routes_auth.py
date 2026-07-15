from __future__ import annotations

from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from server.db.mongo import get_db
from server.services.auth_service import request_otp_challenge, verify_login, hash_password
from server.services.validation import (
    validate_username,
    validate_password,
    validate_name,
    validate_department,
    validate_phone,
    validate_job_role,
)
from server.services.crypto_pki import issue_user_certificate
from server.services.crypto_encrypt import encrypt_fields
from server.services.audit_service import log_event

router = APIRouter(prefix="/auth", tags=["auth"])


def _now():
    return datetime.now(timezone.utc)


class OTPRequest(BaseModel):
    username: str
    password: str


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
    role: str = "employee"  # employee/admin


@router.post("/request-otp")
def request_otp(body: OTPRequest):
    """Password check + OTP issuance.

    Returns otp_token + nonce. In demo mode, the OTP may also be returned to the
    client so the Tkinter UI can show it in a popup.
    """
    try:
        validate_username(body.username)
        if not body.password:
            raise ValueError("Password is required")
        return request_otp_challenge(body.username, body.password)
    except ValueError as e:
        msg = str(e)
        if msg == "Invalid credentials":
            raise HTTPException(status_code=401, detail=msg)
        if msg.startswith("Account is locked"):
            raise HTTPException(status_code=423, detail=msg)
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
        if msg.startswith("Certificate revoked"):
            raise HTTPException(status_code=403, detail=msg)
        if msg.startswith("Account is locked"):
            raise HTTPException(status_code=423, detail=msg)
        raise HTTPException(status_code=400, detail=msg)


@router.post("/register")
def register(body: RegisterRequest):
    """Public registration.

    NOTE: In real deployments, admin registration should be controlled. For this
    academic project, we allow registration for both roles (as requested).
    """
    db = get_db()
    try:
        validate_username(body.username)
        validate_password(body.password)
        validate_name(body.first_name, "First name")
        validate_name(body.last_name, "Last name")
        role = (body.role or "employee").strip().lower()
        if role not in ("employee", "admin"):
            role = "employee"
        validate_job_role(body.job_role, role)
        validate_department(body.department)
        validate_phone(body.phone or "")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if db.users.find_one({"username": body.username}):
        raise HTTPException(status_code=409, detail="Username already exists.")

    cert_info = issue_user_certificate(body.username, body.password, actor_admin=None)

    db.users.insert_one(
        {
            "username": body.username,
            "role": role,
            "job_role": body.job_role,
            # Keep department in users for quick presence display (non-sensitive).
            "department": body.department,
            "password_hash": hash_password(body.password),
            "created_at": _now(),
            "cert_pem": cert_info["cert_pem"],
            "cert_serial": str(cert_info["serial"]),
            "public_key_pem": cert_info["public_key_pem"],
            "pkcs12_path": cert_info["pkcs12_path"],
            "failed_attempts": 0,
            "locked_until": None,
            "presence_state": "offline",
            "last_seen": _now(),
            "active": True,
        }
    )

    profile_doc = {
        "username": body.username,
        "first_name": body.first_name,
        "last_name": body.last_name,
        "job_role": body.job_role,
        "department": body.department,
        "phone": body.phone or "",
        "address": "",
        "updated_at": _now(),
    }
    db.profiles.insert_one(encrypt_fields(profile_doc, fields=["phone", "address"]))

    log_event("USER_REGISTERED", body.username, body.username, "User registered", {"role": role})

    return {
        "ok": True,
        "message": "Registration successful. Your keystore is saved under pki/users/<username>/keystore.p12",
    }
