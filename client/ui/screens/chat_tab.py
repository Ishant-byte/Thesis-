from __future__ import annotations
import tkinter as tk
from tkinter import messagebox

from client.crypto import ChatKeys, new_ephemeral, derive_session_key, encrypt_chat, decrypt_chat, sign_bytes_p12
import secrets
import os
from client.ui.app_config import project_root

def default_keystore_path(username: str) -> str:
    # Robust path resolution regardless of current working directory.
    root = project_root()
    return str(root / "pki" / "users" / username / "keystore.p12")

class ChatTab(tk.Frame):
    def __init__(self, master, dashboard):
        super().__init__(master, bg=dashboard.theme["panel"])
        self.d = dashboard
        self.theme = dashboard.theme

        self.sessions: dict[str, ChatKeys] = {}  # peer -> keys
        self.pending_offers: dict[str, ChatKeys] = {}  # offer_id -> keys

        top = tk.Frame(self, bg=self.theme["panel"])
        top.pack(fill="x", padx=10, pady=10)
        tk.Label(top, text="Private Chat (E2E + disappearing)", fg=self.theme["text"], bg=self.theme["panel"], font=("Segoe UI", 12, "bold")).pack(side="left")

        self.peer_var = tk.StringVar()
        self.peer_menu = tk.OptionMenu(top, self.peer_var, "")
        self.peer_menu.configure(bg=self.theme["bg0"], fg=self.theme["text"], relief="flat", highlightthickness=0)
        self.peer_menu.pack(side="right")

        mid = tk.Frame(self, bg=self.theme["panel"])
        mid.pack(fill="both", expand=True, padx=10)
        self.chat_box = tk.Text(mid, bg=self.theme["bg0"], fg=self.theme["text"], insertbackground=self.theme["text"], relief="flat", wrap="word")
        sb = tk.Scrollbar(mid, orient="vertical", command=self.chat_box.yview)
        self.chat_box.configure(yscrollcommand=sb.set)
        self.chat_box.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        bottom = tk.Frame(self, bg=self.theme["panel"])
        bottom.pack(fill="x", padx=10, pady=10)
        self.exp_var = tk.StringVar(value="Off")
        exp = tk.OptionMenu(bottom, self.exp_var, "Off", "30s", "5m", "1h")
        exp.configure(bg=self.theme["bg0"], fg=self.theme["text"], relief="flat", highlightthickness=0)
        exp.pack(side="left")

        self.msg_entry = tk.Entry(bottom, bg=self.theme["bg0"], fg=self.theme["text"], insertbackground=self.theme["text"], relief="flat")
        self.msg_entry.pack(side="left", fill="x", expand=True, padx=10)
        tk.Button(bottom, text="Send", command=self.send, bg=self.theme["accent"], fg=self.theme["text"], relief="flat").pack(side="right")

        self.d.on_ws(self.on_ws_message)
        self.after(500, self.refresh_peers)

    def refresh_peers(self):
        # build peer list from dashboard presence snapshot
        people = getattr(self.d, "_people", [])
        peers = [p["username"] for p in people if p["username"] != self.d.username]
        menu = self.peer_menu["menu"]
        menu.delete(0, "end")
        for p in peers:
            menu.add_command(label=p, command=lambda v=p: self.peer_var.set(v))
        if peers and not self.peer_var.get():
            self.peer_var.set(peers[0])
        self.after(2000, self.refresh_peers)

    def _append(self, text: str):
        self.chat_box.insert("end", text + "\n")
        self.chat_box.see("end")

    def _expiry_seconds(self) -> int:
        v = self.exp_var.get()
        if v == "30s": return 30
        if v == "5m": return 300
        if v == "1h": return 3600
        return 0

    def ensure_session(self, peer: str) -> ChatKeys:
        if peer in self.sessions and self.sessions[peer].session_key:
            return self.sessions[peer]
        offer_id = secrets.token_urlsafe(10)
        priv, pub_b64 = new_ephemeral()
        ck = ChatKeys(offer_id=offer_id, peer=peer, priv=priv, pub_b64=pub_b64)
        # sign offer data using long-term key
        p12 = default_keystore_path(self.d.username)
        pw = self._prompt_password()
        data = f"chat_offer|{self.d.username}|{peer}|{offer_id}|{pub_b64}".encode("utf-8")
        sig_b64 = sign_bytes_p12(p12, pw, data)
        self.pending_offers[offer_id] = ck
        self.sessions[peer] = ck
        self.d.ws.send({"type":"chat_offer","peer": peer, "offer_id": offer_id, "eph_pub_b64": pub_b64, "sig_b64": sig_b64})
        self._append(f"[*] Starting secure session with {peer} …")
        return ck

    def _prompt_password(self) -> str:
        # reuse login password entry? For simplicity we prompt once per session; user can keep it in clipboard
        import tkinter.simpledialog as sd
        pw = sd.askstring("Keystore Password", "Enter your password to unlock your keystore:", show="•")
        if not pw:
            raise ValueError("Password required")
        return pw

    def send(self):
        peer = self.peer_var.get().strip()
        if not peer:
            return
        text = self.msg_entry.get().strip()
        if not text:
            return
        try:
            ck = self.ensure_session(peer)
            if not ck.session_key:
                self._append("[!] Waiting for peer to accept session…")
                return
            ck.send_counter += 1
            nonce_b64, ct_b64 = encrypt_chat(ck.session_key, text)
            payload = {"nonce_b64": nonce_b64, "ct_b64": ct_b64, "counter": ck.send_counter, "expire_seconds": self._expiry_seconds()}
            self.d.ws.send({"type":"chat_msg","peer": peer, "session_id": ck.offer_id, "payload": payload})
            self._append(f"me → {peer}: {text}")
            self.msg_entry.delete(0,"end")
        except Exception as e:
            messagebox.showerror("Chat", str(e))

    def on_ws_message(self, msg: dict):
        t = msg.get("type")
        if t == "chat_offer":
            sender = msg.get("from")
            offer_id = msg.get("offer_id")
            eph_pub_b64 = msg.get("eph_pub_b64")
            # auto-accept: create our ephemeral, derive after answer sent
            if not sender or not offer_id or not eph_pub_b64:
                return
            try:
                priv, pub_b64 = new_ephemeral()
                ck = ChatKeys(offer_id=offer_id, peer=sender, priv=priv, pub_b64=pub_b64)
                # derive our session key using sender pub
                ck.session_key = derive_session_key(priv, eph_pub_b64, context=offer_id)
                self.sessions[sender] = ck
                # sign answer and send
                p12 = default_keystore_path(self.d.username)
                pw = self._prompt_password()
                data = f"chat_answer|{sender}|{self.d.username}|{offer_id}|{pub_b64}".encode("utf-8")
                sig_b64 = sign_bytes_p12(p12, pw, data)
                self.d.ws.send({"type":"chat_answer","offer_id": offer_id, "eph_pub_b64": pub_b64, "sig_b64": sig_b64})
                self._append(f"[*] Secure session accepted: {sender}")
            except Exception as e:
                self._append(f"[!] Failed to accept session from {sender}: {e}")

        elif t == "chat_answer":
            sender = msg.get("from")
            offer_id = msg.get("offer_id")
            eph_pub_b64 = msg.get("eph_pub_b64")
            if not sender or not offer_id or not eph_pub_b64:
                return
            ck = self.pending_offers.get(offer_id)
            if not ck:
                return
            ck.session_key = derive_session_key(ck.priv, eph_pub_b64, context=offer_id)
            self.pending_offers.pop(offer_id, None)
            self._append(f"[*] Secure session established with {sender}")

        elif t == "chat_msg":
            sender = msg.get("from")
            session_id = msg.get("session_id")
            payload = msg.get("payload", {})
            if not sender or not session_id:
                return
            ck = self.sessions.get(sender)
            if not ck or ck.offer_id != session_id or not ck.session_key:
                return
            try:
                counter = int(payload.get("counter",0))
                if counter <= ck.recv_counter:
                    return  # replay/drop
                ck.recv_counter = counter
                text = decrypt_chat(ck.session_key, payload["nonce_b64"], payload["ct_b64"])
                self._append(f"{sender} → me: {text}")
            except Exception:
                pass

        elif t == "error":
            self._append(f"[server] {msg.get('message')}")
