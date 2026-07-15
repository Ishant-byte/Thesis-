# PramaanHRMS - PKI-secured HRMS (Web + MongoDB)
# --Developer: ISHANT

This is a local-hosted HRMS-style application built to demonstrate PKI-based cryptography:
- Certificate-based authentication (challenge-response)
- Password + OTP (2FA) login
- Key/certificate issuance + revocation (CRL)
- Document signing + verification with signature bundles
- End-to-end encrypted 1:1 chat with disappearing messages (TTL)
- Field-level encryption for sensitive data at rest (AES-256-GCM)
- Admin security/audit logs + user self-logs
- React web UI with a professional corporate design

## 1) Prerequisites
- Python 3.10+
- MongoDB running locally (required)
- Node.js 18+ (for the web client)
- Recommended: create and activate a venv

## 2) Quick setup (Windows PowerShell)
From the project root:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
scripts\bootstrap.ps1
```

## 3) Install dependencies (manual)
```bash
pip install -r requirements.txt
cd web && npm install
```

## 4) Start MongoDB (required)
Default connection: `mongodb://localhost:27017` (DB name: `pramaanhr`).

If MongoDB is not running, the server will refuse to start and the web app will not operate.

## 5) Start the server
```bash
python -m server.app
```

Server startup will:
- Connect to MongoDB
- Create indexes
- Create a local Root CA if missing in `pki/ca/`
- Optionally seed an admin account only when explicitly enabled via environment variables

### Optional: seed an admin user
Admin seeding is disabled by default to avoid hardcoded credentials.

Set the following environment variables before starting the server:
- `SEED_ADMIN_ENABLED=true`
- `SEED_ADMIN_USER=admin@pramaanhr.local`
- `SEED_ADMIN_PASS=<strong-password>`

On first run, this creates the admin user and generates the admin PKCS#12 keystore.

### OTP behavior
During login, the OTP is returned to the web flow for demo convenience.
It is also printed to the server terminal as a fallback.

## 6) Start the web app
```powershell
npm run dev
```

This starts the API server if needed, then starts the React web client.

To start only the web client manually:
```bash
cd web
npm run dev
```

Or from the project root:
```powershell
npm run web
```

Then open `http://localhost:5173` in your browser.

The Vite dev server proxies API calls to `http://127.0.0.1:8765`.

### Web login note
After registration, your keystore is created on the server at `pki/users/<username>/keystore.p12`.
During login, upload this file along with your password to complete certificate verification.
You can also download it from `Profile -> Download Keystore` after signing in.

## 7) Registration
From the Login screen:
- Click Register
- Fill your details; strong password policy is enforced
- After registration, your keystore is saved under `pki/users/<username>/keystore.p12`

Note: Admin accounts are privileged. This build allows Admin self-registration for coursework/demo convenience.

## 8) Document signing and verification
Employee portal -> Documents:
- Sign: browse file -> sign -> export bundle as ZIP
- Verify: upload file + bundle ZIP -> verify signature, hash, certificate chain, CRL

## 9) Chat
Employee/Admin -> Chat:
- Select a user/admin
- Messages are encrypted end-to-end and stored as ciphertext
- Disappearing messages use MongoDB TTL; choose an expiry when sending

## 10) Configuration
Environment variables:
- `MONGO_URI` (default `mongodb://localhost:27017`)
- `MONGO_DB` (default `pramaanhr`)
- `JWT_SECRET` (default generated at runtime; set a value for consistent tokens)
- `SERVER_KEK_PASSPHRASE` (default `change-me`) used to encrypt the server KEK file
- `CORS_ORIGINS` (default `http://localhost:5173,http://127.0.0.1:5173`) for the web client

## 11) Tests
```bash
pytest -q
```

## Security note
This project is built for academic assessment and local-hosted demonstration.
For production, secrets storage, certificate lifecycle, and deployment hardening would need upgrades.
