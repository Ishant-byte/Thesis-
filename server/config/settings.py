from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]  # cipherhr/
PROJECT_DIR = BASE_DIR
PKI_DIR = PROJECT_DIR / "pki"
CA_DIR = PKI_DIR / "ca"
USERS_PKI_DIR = PKI_DIR / "users"

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "pramaanhr")

JWT_SECRET = os.getenv("JWT_SECRET")  # if None, generated at runtime
JWT_ISSUER = "pramaanhr.local"
JWT_TTL_SECONDS = 60 * 60  # 1 hour

# Account lockout
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS = 120  # 2 minutes

# OTP
OTP_TTL_SECONDS = 120  # 2 minutes

# Demo mode: echo OTP back to the client so the Tkinter UI can show it in a popup.
# For production-like behaviour, set OTP_ECHO_TO_CLIENT=false.
OTP_ECHO_TO_CLIENT = os.getenv("OTP_ECHO_TO_CLIENT", "true").strip().lower() in ("1", "true", "yes", "y")

# Server-side key encryption (HSM simulation)
KEK_FILE = PROJECT_DIR / "server" / "config" / "kek.enc"
SERVER_KEK_PASSPHRASE = os.getenv("SERVER_KEK_PASSPHRASE", "change-me")

# Crypto parameters
RSA_KEY_SIZE = 3072
SIGN_ALG = "RSA-PSS-SHA256"
HASH_ALG = "SHA256"
FIELD_ENC_ALG = "AES-256-GCM"

# UI/Client expectations
SERVER_HOST = os.getenv("SERVER_HOST", "127.0.0.1")
SERVER_PORT = int(os.getenv("SERVER_PORT", "8765"))  # HTTP and WS
