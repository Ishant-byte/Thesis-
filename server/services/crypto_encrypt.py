from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Tuple

from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from server.config.settings import KEK_FILE, SERVER_KEK_PASSPHRASE

def _b64e(b: bytes) -> str:
    return base64.b64encode(b).decode("utf-8")

def _b64d(s: str) -> bytes:
    return base64.b64decode(s.encode("utf-8"))

def _derive(passphrase: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=200_000,
    )
    return kdf.derive(passphrase.encode("utf-8"))

def ensure_kek() -> None:
    KEK_FILE.parent.mkdir(parents=True, exist_ok=True)
    if KEK_FILE.exists():
        return
    kek = os.urandom(32)
    salt = os.urandom(16)
    nonce = os.urandom(12)
    wrapping_key = _derive(SERVER_KEK_PASSPHRASE, salt)
    aes = AESGCM(wrapping_key)
    ct = aes.encrypt(nonce, kek, None)
    KEK_FILE.write_text(json.dumps({
        "v": 1,
        "salt": _b64e(salt),
        "nonce": _b64e(nonce),
        "ct": _b64e(ct),
    }, indent=2))

def load_kek() -> bytes:
    ensure_kek()
    doc = json.loads(KEK_FILE.read_text())
    salt = _b64d(doc["salt"])
    nonce = _b64d(doc["nonce"])
    ct = _b64d(doc["ct"])
    wrapping_key = _derive(SERVER_KEK_PASSPHRASE, salt)
    aes = AESGCM(wrapping_key)
    return aes.decrypt(nonce, ct, None)

def wrap_dek(dek: bytes) -> dict:
    kek = load_kek()
    aes = AESGCM(kek)
    nonce = os.urandom(12)
    ct = aes.encrypt(nonce, dek, None)
    return {"alg":"KEK-AESGCM", "nonce": _b64e(nonce), "ct": _b64e(ct)}

def unwrap_dek(wrapped: dict) -> bytes:
    kek = load_kek()
    aes = AESGCM(kek)
    nonce = _b64d(wrapped["nonce"])
    ct = _b64d(wrapped["ct"])
    return aes.decrypt(nonce, ct, None)

def encrypt_value(value: Any, dek: bytes) -> dict:
    aes = AESGCM(dek)
    nonce = os.urandom(12)
    data = json.dumps(value).encode("utf-8")
    ct = aes.encrypt(nonce, data, None)
    return {"alg":"AES-256-GCM", "nonce": _b64e(nonce), "ct": _b64e(ct)}

def decrypt_value(blob: dict, dek: bytes) -> Any:
    aes = AESGCM(dek)
    nonce = _b64d(blob["nonce"])
    ct = _b64d(blob["ct"])
    data = aes.decrypt(nonce, ct, None)
    return json.loads(data.decode("utf-8"))

def encrypt_fields(doc: dict, fields: list[str]) -> dict:
    import os
    dek = os.urandom(32)
    wrapped = wrap_dek(dek)
    out = dict(doc)
    out["_wrapped_dek"] = wrapped
    for f in fields:
        if f in out and out[f] is not None:
            out[f] = encrypt_value(out[f], dek)
    return out

def decrypt_fields(doc: dict, fields: list[str]) -> dict:
    out = dict(doc)
    wrapped = out.get("_wrapped_dek")
    if not wrapped:
        return out
    dek = unwrap_dek(wrapped)
    for f in fields:
        if f in out and isinstance(out[f], dict) and "ct" in out[f]:
            out[f] = decrypt_value(out[f], dek)
    return out
