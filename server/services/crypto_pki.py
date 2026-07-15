from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Tuple, Optional

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

from server.config.settings import CA_DIR, USERS_PKI_DIR, RSA_KEY_SIZE
from server.db.mongo import get_db
from server.services.audit_service import log_event

CA_KEY_PATH = CA_DIR / "ca.key.pem"
CA_CERT_PATH = CA_DIR / "ca.cert.pem"

def _utcnow():
    return datetime.now(timezone.utc)

def ensure_ca() -> None:
    CA_DIR.mkdir(parents=True, exist_ok=True)
    if CA_KEY_PATH.exists() and CA_CERT_PATH.exists():
        return

    key = rsa.generate_private_key(public_exponent=65537, key_size=RSA_KEY_SIZE)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "NP"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "PramaanHR Local CA"),
        x509.NameAttribute(NameOID.COMMON_NAME, "PramaanHR Root CA"),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(_utcnow() - timedelta(days=1))
        .not_valid_after(_utcnow() + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=1), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=True,
            content_commitment=True,
            key_encipherment=True,
            data_encipherment=False,
            key_agreement=False,
            key_cert_sign=True,
            crl_sign=True,
            encipher_only=False,
            decipher_only=False,
        ), critical=True)
        .sign(key, hashes.SHA256())
    )

    CA_KEY_PATH.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    CA_CERT_PATH.write_bytes(cert.public_bytes(serialization.Encoding.PEM))

def load_ca() -> tuple[rsa.RSAPrivateKey, x509.Certificate]:
    ensure_ca()
    key = serialization.load_pem_private_key(CA_KEY_PATH.read_bytes(), password=None)
    cert = x509.load_pem_x509_certificate(CA_CERT_PATH.read_bytes())
    return key, cert

def get_ca_cert_pem() -> str:
    ensure_ca()
    return CA_CERT_PATH.read_text()

def _user_dir(username: str) -> Path:
    d = USERS_PKI_DIR / username
    d.mkdir(parents=True, exist_ok=True)
    return d

def issue_user_certificate(username: str, password: str, actor_admin: str | None = None) -> dict:
    """
    Creates a new user keypair + certificate signed by CA and saves PKCS#12 keystore (password-protected).
    Returns cert_pem, serial (int), pkcs12_path (str), public_key_pem.
    """
    ca_key, ca_cert = load_ca()

    user_key = rsa.generate_private_key(public_exponent=65537, key_size=RSA_KEY_SIZE)
    subject = x509.Name([
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "PramaanHR"),
        x509.NameAttribute(NameOID.COMMON_NAME, username),
    ])

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(user_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(_utcnow() - timedelta(days=1))
        .not_valid_after(_utcnow() + timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=True,
            content_commitment=True,
            key_encipherment=True,
            data_encipherment=True,
            key_agreement=False,
            key_cert_sign=False,
            crl_sign=False,
            encipher_only=False,
            decipher_only=False,
        ), critical=True)
        .sign(ca_key, hashes.SHA256())
    )

    user_dir = _user_dir(username)
    p12_path = user_dir / "keystore.p12"

    p12 = pkcs12.serialize_key_and_certificates(
        name=username.encode(),
        key=user_key,
        cert=cert,
        cas=[ca_cert],
        encryption_algorithm=serialization.BestAvailableEncryption(password.encode("utf-8")),
    )
    p12_path.write_bytes(p12)

    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")
    public_key_pem = user_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode("utf-8")

    serial_str = str(cert.serial_number)

    if actor_admin:
        log_event(
            event_type="CERT_ISSUED",
            actor_username=actor_admin,
            target_username=username,
            message="Certificate issued",
            metadata={"serial": serial_str, "p12_path": str(p12_path)},
        )

    return {
        "cert_pem": cert_pem,
        "serial": serial_str,
        # Store as string to avoid BSON int64 overflow (x509 serials are up to 159-bit)
        "pkcs12_path": str(p12_path),
        "public_key_pem": public_key_pem,
    }

def verify_nonce_signature(nonce: str, signature_b64: str, cert_pem: str) -> bool:
    try:
        cert = x509.load_pem_x509_certificate(cert_pem.encode("utf-8"))
        pub = cert.public_key()
        sig = base64.b64decode(signature_b64.encode("utf-8"))
        pub.verify(
            sig,
            nonce.encode("utf-8"),
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256(),
        )
        return True
    except Exception:
        return False

def get_crl_doc() -> dict:
    db = get_db()
    doc = db.crl.find_one({"_id": "crl"})
    if not doc:
        doc = {"_id": "crl", "revoked_serials": [], "updated_at": _utcnow(), "updated_by": None}
        db.crl.insert_one(doc)
    return doc

def is_revoked(serial: str) -> bool:
    doc = get_crl_doc()
    serial_str = str(serial)
    return serial_str in set(str(x) for x in doc.get("revoked_serials", []))

def revoke_serial(serial: str, actor_admin: str, target_username: str | None = None, reason: str="unspecified") -> None:
    db = get_db()
    doc = get_crl_doc()
    revoked = set(str(x) for x in doc.get("revoked_serials", []))
    serial_str = str(serial)
    revoked.add(serial_str)
    db.crl.update_one({"_id":"crl"}, {"$set": {"revoked_serials": sorted(list(revoked)), "updated_at": _utcnow(), "updated_by": actor_admin}})
    log_event(
        event_type="CERT_REVOKED",
        actor_username=actor_admin,
        target_username=target_username,
        message="Certificate revoked",
        metadata={"serial": serial_str, "reason": reason},
        severity="WARN",
    )

def export_crl_json() -> dict:
    doc = get_crl_doc()
    return {"revoked_serials": [str(x) for x in doc.get("revoked_serials", [])]}


def verify_data_signature(data: bytes, signature_b64: str, cert_pem: str) -> bool:
    """RSA-PSS verify for arbitrary data."""
    try:
        cert = x509.load_pem_x509_certificate(cert_pem.encode("utf-8"))
        pub = cert.public_key()
        sig = base64.b64decode(signature_b64.encode("utf-8"))
        pub.verify(
            sig,
            data,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256(),
        )
        return True
    except Exception:
        return False
