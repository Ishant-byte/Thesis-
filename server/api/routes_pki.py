from __future__ import annotations
from fastapi import APIRouter
from server.services.crypto_pki import get_ca_cert_pem, export_crl_json

router = APIRouter(prefix="/pki", tags=["pki"])

@router.get("/ca.pem")
def ca_pem():
    return {"ca_cert_pem": get_ca_cert_pem()}

@router.get("/crl.json")
def crl_json():
    return export_crl_json()
