from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Tuple

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import pkcs12

def sha256_file(path: Path) -> bytes:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.digest()

def sign_hash_with_pkcs12(pkcs12_path: Path, password: str, digest: bytes) -> tuple[bytes, str]:
    """Returns (signature_bytes, signer_cert_pem)"""
    p12 = pkcs12.load_key_and_certificates(pkcs12_path.read_bytes(), password.encode("utf-8"))
    key = p12[0]
    cert = p12[1]
    if key is None or cert is None:
        raise ValueError("Invalid keystore")
    sig = key.sign(
        digest,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256(),
    )
    return sig, cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")

def verify_signature(cert_pem: str, digest: bytes, signature: bytes) -> bool:
    try:
        cert = x509.load_pem_x509_certificate(cert_pem.encode("utf-8"))
        pub = cert.public_key()
        pub.verify(
            signature,
            digest,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256(),
        )
        return True
    except Exception:
        return False

def build_signature_bundle(
    file_path: Path,
    signature: bytes,
    signer_cert_pem: str,
    ca_cert_pem: str,
    meta: dict[str, Any],
) -> dict[str, Any]:
    digest = sha256_file(file_path)
    return {
        "v": 1,
        "alg": "RSA-PSS-SHA256",
        "hash_alg": "SHA256",
        "file_name": file_path.name,
        "sha256_b64": base64.b64encode(digest).decode("utf-8"),
        "signature_b64": base64.b64encode(signature).decode("utf-8"),
        "cert_pem": signer_cert_pem,
        "ca_cert_pem": ca_cert_pem,
        "meta": meta,
    }

def verify_bundle(file_path: Path, bundle: dict[str, Any]) -> dict[str, Any]:
    digest = sha256_file(file_path)
    expected = base64.b64decode(bundle["sha256_b64"])
    if digest != expected:
        return {"ok": False, "reason": "Hash mismatch (file modified)"}
    sig = base64.b64decode(bundle["signature_b64"])
    cert_pem = bundle["cert_pem"]
    if not verify_signature(cert_pem, digest, sig):
        return {"ok": False, "reason": "Signature invalid"}
    return {"ok": True, "reason": "Verified"}
