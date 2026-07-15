from __future__ import annotations
import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from server.config.settings import OTP_TTL_SECONDS

@dataclass
class OTPRecord:
    username: str
    otp_hash: str
    nonce: str
    expires_at: datetime

_otp_store: Dict[str, OTPRecord] = {}

def _hash(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()

def create_otp(username: str) -> tuple[str, str, str]:
    """Returns (otp_token, otp_code, nonce). OTP code is meant to be printed on server terminal."""
    otp_code = f"{secrets.randbelow(10**6):06d}"
    otp_token = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=OTP_TTL_SECONDS)
    _otp_store[otp_token] = OTPRecord(username=username, otp_hash=_hash(otp_code), nonce=nonce, expires_at=expires_at)
    return otp_token, otp_code, nonce

def pop_and_verify(otp_token: str, otp_code: str) -> Optional[OTPRecord]:
    rec = _otp_store.get(otp_token)
    if not rec:
        return None
    if datetime.now(timezone.utc) > rec.expires_at:
        _otp_store.pop(otp_token, None)
        return None
    if _hash(otp_code) != rec.otp_hash:
        return None
    # valid: consume
    _otp_store.pop(otp_token, None)
    return rec

def get_nonce(otp_token: str) -> Optional[str]:
    rec = _otp_store.get(otp_token)
    if not rec:
        return None
    if datetime.now(timezone.utc) > rec.expires_at:
        _otp_store.pop(otp_token, None)
        return None
    return rec.nonce
