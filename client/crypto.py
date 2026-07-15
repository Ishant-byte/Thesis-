from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from typing import Tuple

from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.asymmetric import x25519

def b64e(b: bytes) -> str:
    return base64.b64encode(b).decode("utf-8")

def b64d(s: str) -> bytes:
    return base64.b64decode(s.encode("utf-8"))

def load_private_key_from_p12(p12_path: str, password: str):
    key, cert, cas = pkcs12.load_key_and_certificates(open(p12_path, "rb").read(), password.encode("utf-8"))
    if key is None:
        raise ValueError("Invalid keystore")
    return key

def sign_text_p12(p12_path: str, password: str, text: str) -> str:
    key = load_private_key_from_p12(p12_path, password)
    sig = key.sign(
        text.encode("utf-8"),
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256(),
    )
    return b64e(sig)

def sign_bytes_p12(p12_path: str, password: str, data: bytes) -> str:
    key = load_private_key_from_p12(p12_path, password)
    sig = key.sign(
        data,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256(),
    )
    return b64e(sig)

@dataclass
class ChatKeys:
    offer_id: str
    peer: str
    priv: x25519.X25519PrivateKey
    pub_b64: str
    session_key: bytes | None = None
    send_counter: int = 0
    recv_counter: int = 0

def new_ephemeral() -> Tuple[x25519.X25519PrivateKey, str]:
    priv = x25519.X25519PrivateKey.generate()
    pub = priv.public_key().public_bytes_raw()
    return priv, b64e(pub)

def derive_session_key(priv: x25519.X25519PrivateKey, peer_pub_b64: str, context: str) -> bytes:
    peer_pub = x25519.X25519PublicKey.from_public_bytes(b64d(peer_pub_b64))
    shared = priv.exchange(peer_pub)
    hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=context.encode("utf-8"))
    return hkdf.derive(shared)

def encrypt_chat(session_key: bytes, plaintext: str) -> tuple[str, str]:
    aes = AESGCM(session_key)
    nonce = os.urandom(12)
    ct = aes.encrypt(nonce, plaintext.encode("utf-8"), None)
    return b64e(nonce), b64e(ct)

def decrypt_chat(session_key: bytes, nonce_b64: str, ct_b64: str) -> str:
    aes = AESGCM(session_key)
    pt = aes.decrypt(b64d(nonce_b64), b64d(ct_b64), None)
    return pt.decode("utf-8")
