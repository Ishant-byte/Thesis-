from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from server.config.settings import SERVER_HOST, SERVER_PORT
from server.db.mongo import get_db
from server.db.indexes import ensure_indexes
from server.services.crypto_pki import ensure_ca, issue_user_certificate, is_revoked, verify_data_signature
from server.services.crypto_encrypt import ensure_kek
from server.services.auth_service import hash_password, decode_jwt
from server.services.audit_service import log_event

from server.api.routes_auth import router as auth_router
from server.api.routes_admin import router as admin_router
from server.api.routes_employee import router as employee_router
from server.api.routes_pki import router as pki_router

def _now():
    return datetime.now(timezone.utc)

def seed_admin():
    db = get_db()
    # Admin seeding is a development convenience and MUST NOT rely on hardcoded
    # credentials. For safety, seed only when explicitly enabled via environment.
    #
    # Usage (example):
    #   SEED_ADMIN_ENABLED=true
    #   SEED_ADMIN_USER=admin@pramaanhr.local
    #   SEED_ADMIN_PASS=<strong-password>
    enabled = os.getenv("SEED_ADMIN_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    seed_user = os.getenv("SEED_ADMIN_USER", "").strip()
    seed_pass = os.getenv("SEED_ADMIN_PASS", "").strip()

    if not enabled:
        return
    if not seed_user or not seed_pass:
        print("[PramaanHR] Admin seeding enabled, but SEED_ADMIN_USER/SEED_ADMIN_PASS are missing. Skipping.")
        return
    if db.users.find_one({"username": seed_user}):
        return

    cert_info = issue_user_certificate(seed_user, seed_pass, actor_admin=None)
    db.users.insert_one({
        "username": seed_user,
        "role": "admin",
        "job_role": "System Administrator",
        "department": "Security",
        "password_hash": hash_password(seed_pass),
        "created_at": _now(),
        "cert_pem": cert_info["cert_pem"],
        "cert_serial": str(cert_info["serial"]),
        "public_key_pem": cert_info["public_key_pem"],
        "pkcs12_path": cert_info["pkcs12_path"],
        "failed_attempts": 0,
        "locked_until": None,
        "presence_state": "offline",
        "last_seen": _now(),
        "active": True,
    })
    from server.services.crypto_encrypt import encrypt_fields
    db.profiles.insert_one(encrypt_fields({
        "username": seed_user,
        "first_name": "System",
        "last_name": "Admin",
        "department": "Security",
        "phone": "",
        "address": "",
        "updated_at": _now(),
    }, fields=["phone","address"]))
    log_event("ADMIN_SEEDED", seed_user, seed_user, "Admin seeded", {"username": seed_user})
    print("[PramaanHR] Seeded admin user:")
    print("  username:", seed_user)
    print("  keystore:", cert_info["pkcs12_path"])
    print("  note: password is taken from SEED_ADMIN_PASS (not printed)")

app = FastAPI(title="PramaanHR Server", version="1.0")

_cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(employee_router)
app.include_router(pki_router)

@app.get("/health")
def health():
    # if Mongo is down, get_db() would have exited at startup
    return {"ok": True, "time": _now().isoformat()}

# --------------------------
# WebSocket: presence + chat
# --------------------------

class WSManager:
    def __init__(self):
        self.connections: Dict[str, WebSocket] = {}  # username -> ws
        self.sessions: Dict[str, dict] = {}  # offer_id -> session temp

    async def connect(self, username: str, ws: WebSocket):
        await ws.accept()
        self.connections[username] = ws
        await self.set_presence(username, "online")
        await self.broadcast_presence()

    async def disconnect(self, username: str):
        if username in self.connections:
            self.connections.pop(username, None)
        await self.set_presence(username, "offline")
        await self.broadcast_presence()

    async def send(self, username: str, payload: dict):
        ws = self.connections.get(username)
        if ws:
            await ws.send_text(json.dumps(payload))

    async def broadcast(self, payload: dict):
        msg = json.dumps(payload)
        for ws in list(self.connections.values()):
            try:
                await ws.send_text(msg)
            except Exception:
                pass

    async def set_presence(self, username: str, state: str):
        db = get_db()
        db.users.update_one({"username": username}, {"$set": {"presence_state": state, "last_seen": _now()}})
        log_event("PRESENCE", username, username, "Presence updated", {"state": state})

    async def broadcast_presence(self):
        db = get_db()
        # Build a lightweight profile map so we can show department/job_role
        # in presence without exposing sensitive fields.
        prof_map = {}
        try:
            for p in db.profiles.find({}, {"username": 1, "department": 1, "job_role": 1}):
                if p.get("username"):
                    prof_map[p["username"]] = {
                        "department": p.get("department") or "",
                        "job_role": p.get("job_role") or "",
                    }
        except Exception:
            prof_map = {}

        people = []
        for u in db.users.find({}, {"password_hash":0, "cert_pem":0, "public_key_pem":0, "pkcs12_path":0}):
            uname = u.get("username")
            pm = prof_map.get(uname, {}) if uname else {}
            people.append({
                "username": uname,
                "role": u.get("role", "employee"),
                "department": u.get("department") or pm.get("department", ""),
                "job_role": u.get("job_role") or pm.get("job_role", ""),
                "presence_state": u.get("presence_state","offline"),
                "last_seen": u.get("last_seen").isoformat() if u.get("last_seen") else None
            })
        await self.broadcast({"type":"presence_list", "people": people})

manager = WSManager()

def _auth_from_token(token: str) -> dict:
    payload = decode_jwt(token)
    return payload

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    token = ws.query_params.get("token", "")
    if not token:
        await ws.close(code=4401)
        return
    try:
        payload = _auth_from_token(token)
    except Exception:
        await ws.close(code=4401)
        return
    username = payload["sub"]
    role = payload.get("role","employee")

    await manager.connect(username, ws)

    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            mtype = msg.get("type")

            if mtype == "set_status":
                state = msg.get("status","online")
                await manager.set_presence(username, state)
                await manager.broadcast_presence()

            elif mtype == "chat_offer":
                # Sender offers ephemeral pubkey to peer
                peer = msg.get("peer")
                offer_id = msg.get("offer_id")
                eph_pub_b64 = msg.get("eph_pub_b64")
                sig_b64 = msg.get("sig_b64")
                if not peer or not offer_id or not eph_pub_b64 or not sig_b64:
                    await manager.send(username, {"type":"error","message":"Invalid chat_offer"})
                    continue
                db = get_db()
                sender = db.users.find_one({"username": username})
                if not sender:
                    continue
                serial = sender.get("cert_serial")
                if serial and is_revoked(str(serial)):
                    await manager.send(username, {"type":"error","message":"Your certificate is revoked."})
                    continue
                data = f"chat_offer|{username}|{peer}|{offer_id}|{eph_pub_b64}".encode("utf-8")
                if not verify_data_signature(data, sig_b64, sender["cert_pem"]):
                    await manager.send(username, {"type":"error","message":"Invalid signature on chat_offer"})
                    continue
                # store offer
                manager.sessions[offer_id] = {"a": username, "b": peer, "a_pub": eph_pub_b64, "created_at": _now().isoformat()}
                # relay if peer online
                await manager.send(peer, {"type":"chat_offer","from": username, "offer_id": offer_id, "eph_pub_b64": eph_pub_b64, "sig_b64": sig_b64})

            elif mtype == "chat_answer":
                offer_id = msg.get("offer_id")
                eph_pub_b64 = msg.get("eph_pub_b64")
                sig_b64 = msg.get("sig_b64")
                if not offer_id or not eph_pub_b64 or not sig_b64:
                    await manager.send(username, {"type":"error","message":"Invalid chat_answer"})
                    continue
                sess = manager.sessions.get(offer_id)
                if not sess or sess.get("b") != username:
                    await manager.send(username, {"type":"error","message":"Unknown offer_id"})
                    continue
                db = get_db()
                responder = db.users.find_one({"username": username})
                if not responder:
                    continue
                serial = responder.get("cert_serial")
                if serial and is_revoked(str(serial)):
                    await manager.send(username, {"type":"error","message":"Your certificate is revoked."})
                    continue
                data = f"chat_answer|{sess['a']}|{username}|{offer_id}|{eph_pub_b64}".encode("utf-8")
                if not verify_data_signature(data, sig_b64, responder["cert_pem"]):
                    await manager.send(username, {"type":"error","message":"Invalid signature on chat_answer"})
                    continue
                # relay to initiator
                await manager.send(sess["a"], {"type":"chat_answer","from": username, "offer_id": offer_id, "eph_pub_b64": eph_pub_b64, "sig_b64": sig_b64})
                # optional: keep session in memory (client holds keys); we keep for a bit
                sess["b_pub"] = eph_pub_b64

            elif mtype == "chat_msg":
                # ciphertext relay + store
                peer = msg.get("peer")
                session_id = msg.get("session_id")
                payload = msg.get("payload")  # {nonce_b64, ct_b64, counter, expire_seconds}
                if not peer or not session_id or not isinstance(payload, dict):
                    await manager.send(username, {"type":"error","message":"Invalid chat_msg"})
                    continue
                expire_seconds = int(payload.get("expire_seconds", 0))
                expireAt = None
                if expire_seconds > 0:
                    expireAt = _now() + timedelta(seconds=min(expire_seconds, 24*3600))
                db = get_db()
                db.chat_messages.insert_one({
                    "session_id": session_id,
                    "from": username,
                    "to": peer,
                    "payload": payload,
                    "created_at": _now(),
                    "expireAt": expireAt,
                })
                await manager.send(peer, {"type":"chat_msg","from": username, "session_id": session_id, "payload": payload})

            elif mtype == "ping":
                await manager.send(username, {"type":"pong","time": _now().isoformat()})

            else:
                await manager.send(username, {"type":"error","message":"Unknown message type"})

    except WebSocketDisconnect:
        await manager.disconnect(username)
    except Exception:
        await manager.disconnect(username)

def main():
    # init
    ensure_ca()
    ensure_kek()
    ensure_indexes()
    seed_admin()
    uvicorn.run("server.app:app", host=SERVER_HOST, port=SERVER_PORT, log_level="info")

if __name__ == "__main__":
    main()
