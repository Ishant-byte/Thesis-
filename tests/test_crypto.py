from __future__ import annotations
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography import x509
from cryptography.x509.oid import NameOID
from datetime import datetime, timedelta, timezone

from server.services.crypto_sign import sign_hash_with_pkcs12, verify_signature
from server.api.deps import require_admin, require_super_admin
from server.api.routes_admin import _require_can_manage_account
from fastapi import HTTPException
import pytest


def test_admin_role_boundaries():
    assert require_admin({"role": "admin"})["role"] == "admin"
    assert require_admin({"role": "super_admin"})["role"] == "super_admin"
    with pytest.raises(HTTPException):
        require_admin({"role": "employee"})
    with pytest.raises(HTTPException):
        require_super_admin({"role": "admin"})
    assert require_super_admin({"role": "super_admin"})["role"] == "super_admin"
    _require_can_manage_account({"role": "admin"}, {"role": "employee"})
    _require_can_manage_account({"role": "super_admin"}, {"role": "admin"})
    with pytest.raises(HTTPException):
        _require_can_manage_account({"role": "admin"}, {"role": "admin"})
    with pytest.raises(HTTPException):
        _require_can_manage_account({"role": "super_admin"}, {"role": "super_admin"})

def test_pkcs12_sign_roundtrip():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test@example.com")])
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(timezone.utc) - timedelta(days=1))
            .not_valid_after(datetime.now(timezone.utc) + timedelta(days=30))
            .sign(key, hashes.SHA256())
        )
        p12 = pkcs12.serialize_key_and_certificates(
            name=b"test",
            key=key,
            cert=cert,
            cas=None,
            encryption_algorithm=serialization.BestAvailableEncryption(b"Passw0rd!"),
        )
        p12_path = td/"k.p12"
        p12_path.write_bytes(p12)
        digest = b"document digest"
        signature, cert_pem = sign_hash_with_pkcs12(p12_path, "Passw0rd!", digest)
        assert verify_signature(cert_pem, digest, signature)
