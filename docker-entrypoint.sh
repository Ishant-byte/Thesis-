#!/usr/bin/env sh
set -e

# Ensure PKI dirs exist (bind-mounted)
mkdir -p /app/pki/ca /app/pki/users

echo "[PramaanHR] Waiting for MongoDB..."
python - <<'PY'
import os, time
from pymongo import MongoClient

uri = os.environ.get("MONGO_URI", "mongodb://mongo:27017")
deadline = time.time() + 60

while True:
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=2000)
        client.admin.command("ping")
        break
    except Exception as e:
        if time.time() > deadline:
            raise SystemExit(f"[PramaanHR] MongoDB not ready after 60s: {e}")
        time.sleep(2)

print("[PramaanHR] MongoDB is ready.")
PY

exec python -m server.app
