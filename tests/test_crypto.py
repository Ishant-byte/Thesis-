from __future__ import annotations
import os
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography import x509
from cryptography.x509.oid import NameOID
from datetime import datetime, timedelta, timezone

from client.crypto import new_ephemeral, derive_session_key, encrypt_chat, decrypt_chat, sign_text_p12

def test_chat_key_agreement_and_encrypt():
    privA, pubA = new_ephemeral()
    privB, pubB = new_ephemeral()
    kA = derive_session_key(privA, pubB, context="sess1")
    kB = derive_session_key(privB, pubA, context="sess1")
    assert kA == kB
    n, ct = encrypt_chat(kA, "hello")
    assert decrypt_chat(kB, n, ct) == "hello"

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
        sig_b64 = sign_text_p12(str(p12_path), "Passw0rd!", "nonce")
        assert isinstance(sig_b64, str) and len(sig_b64) > 10
