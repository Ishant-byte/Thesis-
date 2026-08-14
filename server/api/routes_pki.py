from __future__ import annotations
import base64

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field, field_validator

from server.services.crypto_pki import get_ca_cert_pem, export_crl_json
from server.services.crypto_sign import MAX_BUNDLE_BYTES, MAX_DOCUMENT_BYTES, verify_v2_document_bundle

router = APIRouter(prefix="/pki", tags=["pki"])


class PKIVerificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    document_b64: str = Field(min_length=1, max_length=4 * ((MAX_DOCUMENT_BYTES + 2) // 3))
    bundle_b64: str = Field(min_length=1, max_length=4 * ((MAX_BUNDLE_BYTES + 2) // 3))

    @field_validator("document_b64", "bundle_b64")
    @classmethod
    def validate_base64(cls, value: str) -> str:
        try:
            base64.b64decode(value.encode("ascii"), validate=True)
        except Exception as exc:
            raise ValueError("Must be standard base64.") from exc
        return value


class PKICheckResult(BaseModel):
    ok: bool
    detail: str


class PKIVerificationResponse(BaseModel):
    verified: bool
    status: str
    protocol_version: int | None = None
    signer_identity: str | None = None
    signer_serial: str | None = None
    checks: dict[str, PKICheckResult]

@router.get("/ca.pem")
def ca_pem():
    return {"ca_cert_pem": get_ca_cert_pem()}

@router.get("/crl.json")
def crl_json():
    return export_crl_json()


@router.post("/verify", response_model=PKIVerificationResponse)
def verify_document_signature(body: PKIVerificationRequest):
    document_bytes = base64.b64decode(body.document_b64.encode("ascii"), validate=True)
    bundle_bytes = base64.b64decode(body.bundle_b64.encode("ascii"), validate=True)
    result = verify_v2_document_bundle(document_bytes, bundle_bytes)
    return PKIVerificationResponse.model_validate(result)
