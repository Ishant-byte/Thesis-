from __future__ import annotations

import base64
import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509 import BasicConstraints, KeyUsage
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from server.services.crypto_pki import (
    canonicalize_serial,
    certificate_common_name,
    certificate_serial,
    get_user_certificate_enrollment,
    is_revoked,
    load_ca,
)

V2_PROTOCOL_VERSION = 2
V2_PURPOSE = "pramaanhr.document-signature"
V2_SIGNATURE_ALGORITHM = "RSA-PSS-SHA256"
V2_HASH_ALGORITHM = "SHA-256"
V2_REQUIRED_BUNDLE_FILES = frozenset({"manifest.json", "signature.sig", "signer_cert.pem"})
MAX_DOCUMENT_BYTES = 25 * 1024 * 1024
MAX_BUNDLE_BYTES = 1024 * 1024
MAX_BUNDLE_ENTRY_BYTES = 256 * 1024


class V2Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    v: int
    purpose: str
    hash_alg: str
    signature_alg: str
    sha256_b64: str
    signer_cert_sha256_b64: str

    @field_validator("v")
    @classmethod
    def validate_version(cls, value: int) -> int:
        if value != V2_PROTOCOL_VERSION:
            raise ValueError(f"Unsupported protocol version: {value}")
        return value

    @field_validator("purpose")
    @classmethod
    def validate_purpose(cls, value: str) -> str:
        if value != V2_PURPOSE:
            raise ValueError(f"Unsupported purpose: {value}")
        return value

    @field_validator("hash_alg")
    @classmethod
    def validate_hash_alg(cls, value: str) -> str:
        if value != V2_HASH_ALGORITHM:
            raise ValueError(f"Unsupported hash algorithm: {value}")
        return value

    @field_validator("signature_alg")
    @classmethod
    def validate_signature_alg(cls, value: str) -> str:
        if value != V2_SIGNATURE_ALGORITHM:
            raise ValueError(f"Unsupported signature algorithm: {value}")
        return value

    @field_validator("sha256_b64", "signer_cert_sha256_b64")
    @classmethod
    def validate_base64_field(cls, value: str) -> str:
        _decode_base64(value)
        return value

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


def verify_v2_document_bundle(
    document_bytes: bytes,
    bundle_bytes: bytes,
    *,
    now: datetime | None = None,
    load_ca_func: Callable[[], tuple[Any, x509.Certificate]] = load_ca,
    is_revoked_func: Callable[[str], bool] | None = None,
    get_user_certificate_enrollment_func: Callable[[str], dict[str, Any] | None] = get_user_certificate_enrollment,
) -> dict[str, Any]:
    is_revoked_func = is_revoked_func or (lambda serial: is_revoked(serial, create_if_missing=False))
    checks = _default_checks()
    protocol_version: int | None = None
    signer_identity: str | None = None
    signer_serial: str | None = None

    if len(document_bytes) > MAX_DOCUMENT_BYTES:
        _set_check(checks, "bundle", False, "Document exceeds the 25 MiB verification limit.")
        return _build_result(checks, protocol_version, signer_identity, signer_serial)
    if len(bundle_bytes) > MAX_BUNDLE_BYTES:
        _set_check(checks, "bundle", False, "Signature bundle exceeds the 1 MiB verification limit.")
        return _build_result(checks, protocol_version, signer_identity, signer_serial)

    try:
        bundle = _read_bundle(bundle_bytes)
        _set_check(checks, "bundle", True, "Bundle parsed with required v2 entries.")
    except ValueError as exc:
        _set_check(checks, "bundle", False, str(exc))
        return _build_result(checks, protocol_version, signer_identity, signer_serial)

    manifest_bytes = bundle["manifest.json"]
    try:
        manifest = _load_manifest(manifest_bytes)
        protocol_version = manifest.v
    except ValueError as exc:
        _set_check(checks, "manifest", False, str(exc))
        return _build_result(checks, protocol_version, signer_identity, signer_serial)

    canonical_manifest = _canonical_manifest_bytes(manifest)
    if manifest_bytes != canonical_manifest:
        _set_check(checks, "manifest", False, "Manifest is not in canonical deterministic JSON form.")
        return _build_result(checks, protocol_version, signer_identity, signer_serial)

    signature_bytes = bundle["signature.sig"]
    if not signature_bytes:
        _set_check(checks, "signature", False, "Signature file is empty.")
        return _build_result(checks, protocol_version, signer_identity, signer_serial)

    try:
        signer_cert = x509.load_pem_x509_certificate(bundle["signer_cert.pem"])
    except Exception:
        _set_check(checks, "certificate_trust", False, "Signer certificate is not valid PEM X.509.")
        return _build_result(checks, protocol_version, signer_identity, signer_serial)

    signer_identity = certificate_common_name(signer_cert)
    signer_serial = certificate_serial(signer_cert)

    manifest_cert_fp = _decode_base64(manifest.signer_cert_sha256_b64)
    actual_cert_fp = _certificate_fingerprint(signer_cert)
    if actual_cert_fp != manifest_cert_fp:
        _set_check(checks, "manifest", False, "Manifest signer certificate fingerprint does not match the bundled certificate.")
        return _build_result(checks, protocol_version, signer_identity, signer_serial)

    _set_check(checks, "manifest", True, "Manifest is canonical and bound to the bundled signer certificate.")

    document_digest = hashlib.sha256(document_bytes).digest()
    if document_digest != _decode_base64(manifest.sha256_b64):
        _set_check(checks, "document_integrity", False, "Document digest does not match the signed manifest.")
        return _build_result(checks, protocol_version, signer_identity, signer_serial)
    _set_check(checks, "document_integrity", True, "Document digest matches the signed manifest.")

    if not verify_signature(bundle["signer_cert.pem"].decode("utf-8"), canonical_manifest, signature_bytes):
        _set_check(checks, "signature", False, "RSA-PSS signature over the canonical manifest is invalid.")
        return _build_result(checks, protocol_version, signer_identity, signer_serial)
    _set_check(checks, "signature", True, "RSA-PSS signature over the canonical manifest is valid.")

    trust_error = _verify_direct_ca_trust(signer_cert, load_ca_func)
    if trust_error:
        _set_check(checks, "certificate_trust", False, trust_error)
        return _build_result(checks, protocol_version, signer_identity, signer_serial)
    _set_check(checks, "certificate_trust", True, "Signer certificate is issued directly by the configured PramaanHR CA.")

    validity_error = _verify_certificate_validity(signer_cert, now)
    if validity_error:
        _set_check(checks, "certificate_validity", False, validity_error)
        return _build_result(checks, protocol_version, signer_identity, signer_serial)
    _set_check(checks, "certificate_validity", True, "Signer certificate is a currently valid end-entity signing certificate.")

    if is_revoked_func(signer_serial):
        _set_check(checks, "revocation", False, f"Certificate serial {signer_serial} is revoked.")
        return _build_result(checks, protocol_version, signer_identity, signer_serial)
    _set_check(checks, "revocation", True, f"Certificate serial {signer_serial} is not revoked.")

    if not signer_identity:
        _set_check(checks, "signer_identity", False, "Signer certificate does not contain a Common Name identity.")
        return _build_result(checks, protocol_version, signer_identity, signer_serial)
    _set_check(checks, "signer_identity", True, f"Signer identity derived from certificate CN: {signer_identity}.")

    enrollment_error = _verify_enrollment(
        signer_identity,
        signer_serial,
        actual_cert_fp,
        get_user_certificate_enrollment_func,
    )
    if enrollment_error:
        _set_check(checks, "enrollment", False, enrollment_error)
        return _build_result(checks, protocol_version, signer_identity, signer_serial)
    _set_check(checks, "enrollment", True, "Signer certificate matches authoritative PramaanHR enrollment state.")

    return _build_result(checks, protocol_version, signer_identity, signer_serial)

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


def _default_checks() -> dict[str, dict[str, Any]]:
    return {
        "bundle": {"ok": False, "detail": "Not evaluated."},
        "manifest": {"ok": False, "detail": "Not evaluated."},
        "document_integrity": {"ok": False, "detail": "Not evaluated."},
        "signature": {"ok": False, "detail": "Not evaluated."},
        "certificate_trust": {"ok": False, "detail": "Not evaluated."},
        "certificate_validity": {"ok": False, "detail": "Not evaluated."},
        "revocation": {"ok": False, "detail": "Not evaluated."},
        "signer_identity": {"ok": False, "detail": "Not evaluated."},
        "enrollment": {"ok": False, "detail": "Not evaluated."},
    }


def _set_check(checks: dict[str, dict[str, Any]], name: str, ok: bool, detail: str) -> None:
    checks[name] = {"ok": ok, "detail": detail}


def _build_result(
    checks: dict[str, dict[str, Any]],
    protocol_version: int | None,
    signer_identity: str | None,
    signer_serial: str | None,
) -> dict[str, Any]:
    verified = all(item["ok"] for item in checks.values())
    return {
        "verified": verified,
        "status": "verified" if verified else "rejected",
        "protocol_version": protocol_version,
        "signer_identity": signer_identity,
        "signer_serial": signer_serial,
        "checks": checks,
    }


def _read_bundle(bundle_bytes: bytes) -> dict[str, bytes]:
    try:
        with zipfile.ZipFile(io.BytesIO(bundle_bytes)) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise ValueError("Bundle contains duplicate ZIP entry names.")
            normalized = {name.replace("\\", "/") for name in names}
            if normalized == {"bundle.json"}:
                raise ValueError("Legacy v1 bundles are not accepted by the v2 verifier.")
            if normalized != V2_REQUIRED_BUNDLE_FILES:
                raise ValueError("Bundle must contain exactly manifest.json, signature.sig, and signer_cert.pem.")
            files: dict[str, bytes] = {}
            for name in names:
                clean_name = name.replace("\\", "/")
                if clean_name.startswith("/") or ".." in clean_name.split("/"):
                    raise ValueError("Bundle contains invalid ZIP entry paths.")
                info = archive.getinfo(name)
                if info.is_dir():
                    raise ValueError("Bundle must not contain directory entries.")
                if info.file_size > MAX_BUNDLE_ENTRY_BYTES or info.compress_size > MAX_BUNDLE_ENTRY_BYTES:
                    raise ValueError("Bundle ZIP entry exceeds the 256 KiB limit.")
                files[clean_name] = archive.read(name)
            return files
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError, OSError) as exc:
        raise ValueError("Bundle is not a readable ZIP archive.") from exc


def _load_manifest(manifest_bytes: bytes) -> V2Manifest:
    try:
        manifest_text = manifest_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Manifest must be valid UTF-8 JSON.") from exc
    try:
        payload = json.loads(manifest_text, object_pairs_hook=_reject_duplicate_json_keys)
    except ValueError as exc:
        raise ValueError(f"Manifest JSON is invalid: {exc}") from exc
    try:
        return V2Manifest.model_validate(payload)
    except ValidationError as exc:
        first_error = exc.errors()[0]
        loc = ".".join(str(part) for part in first_error.get("loc", ())) or "manifest"
        raise ValueError(f"Manifest validation failed at {loc}: {first_error.get('msg', 'invalid value')}") from exc


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"duplicate key {key!r}")
        out[key] = value
    return out


def _canonical_manifest_bytes(manifest: V2Manifest) -> bytes:
    return json.dumps(
        manifest.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _decode_base64(value: str) -> bytes:
    try:
        return base64.b64decode(value.encode("ascii"), validate=True)
    except Exception as exc:
        raise ValueError("Field must be standard base64.") from exc


def _certificate_fingerprint(cert: x509.Certificate) -> bytes:
    return hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).digest()


def _verify_direct_ca_trust(
    cert: x509.Certificate,
    load_ca_func: Callable[[], tuple[Any, x509.Certificate]],
) -> str | None:
    _, ca_cert = load_ca_func()
    if cert.issuer != ca_cert.subject:
        return "Signer certificate issuer does not match the configured PramaanHR CA."
    try:
        ca_cert.public_key().verify(
            cert.signature,
            cert.tbs_certificate_bytes,
            padding.PKCS1v15(),
            cert.signature_hash_algorithm,
        )
    except Exception:
        return "Signer certificate was not signed by the configured PramaanHR CA."
    return None


def _verify_certificate_validity(cert: x509.Certificate, now: datetime | None) -> str | None:
    if cert.subject == cert.issuer:
        return "Signer certificate is self-signed."
    try:
        basic_constraints = cert.extensions.get_extension_for_class(BasicConstraints).value
    except x509.ExtensionNotFound:
        return "Signer certificate is missing BasicConstraints."
    if basic_constraints.ca:
        return "CA certificates cannot be used as document signers."
    try:
        key_usage = cert.extensions.get_extension_for_class(KeyUsage).value
    except x509.ExtensionNotFound:
        return "Signer certificate is missing KeyUsage."
    if not key_usage.digital_signature:
        return "Signer certificate does not permit digital signatures."
    now = now or datetime.now(timezone.utc)
    not_before = _certificate_not_valid_before(cert)
    not_after = _certificate_not_valid_after(cert)
    if now < not_before:
        return "Signer certificate is not yet valid."
    if now > not_after:
        return "Signer certificate has expired."
    return None


def _certificate_not_valid_before(cert: x509.Certificate) -> datetime:
    if hasattr(cert, "not_valid_before_utc"):
        return cert.not_valid_before_utc
    return cert.not_valid_before.replace(tzinfo=timezone.utc)


def _certificate_not_valid_after(cert: x509.Certificate) -> datetime:
    if hasattr(cert, "not_valid_after_utc"):
        return cert.not_valid_after_utc
    return cert.not_valid_after.replace(tzinfo=timezone.utc)


def _verify_enrollment(
    identity: str,
    serial: str,
    fingerprint: bytes,
    get_user_certificate_enrollment_func: Callable[[str], dict[str, Any] | None],
) -> str | None:
    enrollment = get_user_certificate_enrollment_func(identity)
    if not enrollment:
        return f"No PramaanHR enrollment exists for signer identity {identity}."
    if not enrollment.get("active", True):
        return f"Signer identity {identity} is not active in PramaanHR enrollment state."
    try:
        enrolled_serial = canonicalize_serial(enrollment.get("cert_serial", ""))
    except ValueError:
        return f"Stored enrollment serial for {identity} is invalid."
    if enrolled_serial != serial:
        return f"Signer serial {serial} does not match enrolled serial {enrolled_serial}."
    enrolled_pem = enrollment.get("cert_pem")
    if not enrolled_pem:
        return f"Stored enrollment certificate for {identity} is missing."
    try:
        enrolled_cert = x509.load_pem_x509_certificate(enrolled_pem.encode("utf-8"))
    except Exception:
        return f"Stored enrollment certificate for {identity} is invalid."
    if _certificate_fingerprint(enrolled_cert) != fingerprint:
        return f"Bundled signer certificate does not match the enrolled certificate for {identity}."
    return None
