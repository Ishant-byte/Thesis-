from __future__ import annotations
import os
import re
from pathlib import Path
import tkinter as tk
from tkinter import messagebox

from client import api
from client.crypto import sign_text_p12
from client.ui.widgets.base import AnimatedBackground, make_button, make_label, make_entry
from client.ui.themes.themes import ADMIN_THEME, USER_THEME

def keystore_path(username: str) -> str:
    """Return absolute path to the user's PKCS#12 keystore.

    Robustly locates the project root by walking up from this file until we find
    a folder that contains `pki/`, `client/`, and `server/`.
    """
    here = Path(__file__).resolve()
    root: Path | None = None
    for parent in [here.parent] + list(here.parents):
        if (parent / "pki").exists() and (parent / "client").exists() and (parent / "server").exists():
            root = parent
            break
    if root is None:
        # Fallback: <root>/client/ui/screens/login.py -> parents[3] == <root>
        root = here.parents[3]
    return str(root / "pki" / "users" / username / "keystore.p12")


EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

class LoginScreen(tk.Frame):
    def __init__(self, master, portal_role: str, on_login_success, on_back=None, on_register=None):
        super().__init__(master)
        self.portal_role = portal_role  # "admin" or "employee"
        self.on_login_success = on_login_success
        self.on_back = on_back
        self.on_register = on_register
        base_theme = ADMIN_THEME if portal_role == "admin" else USER_THEME
        # Persist light/dark preference per portal on the root App (if present)
        pref = True
        try:
            pref = bool(getattr(master, "portal_dark_mode", {}).get(portal_role, True))
        except Exception:
            pref = True
        self.dark_mode = pref
        # Apply light mode by swapping bg0/bg1/panel.
        if self.dark_mode:
            self.theme = base_theme
        else:
            t = dict(base_theme)
            t["bg0"], t["bg1"] = t["bg1"], t["bg0"]
            t["panel"] = t["bg1"]
            self.theme = t

        self.pack(fill="both", expand=True)
        self.bg = AnimatedBackground(self, self.theme)
        self.bg.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.bg.start()

        panel = tk.Frame(self, bg=self.theme["panel"])
        panel.place(relx=0.5, rely=0.5, anchor="center", width=560, height=420)

        make_label(panel, "Login", self.theme, size=20, bold=True).pack(pady=(24,6))
        make_label(panel, f"{'Admin' if portal_role=='admin' else 'Employee'} Portal", self.theme, size=11).pack(pady=(0,16))

        form = tk.Frame(panel, bg=self.theme["panel"])
        form.pack(pady=10, padx=40, fill="x")

        make_label(form, "Username (email)", self.theme, size=10).grid(row=0, column=0, sticky="w")
        self.user_entry = make_entry(form, self.theme)
        self.user_entry.grid(row=1, column=0, sticky="ew", pady=(6, 14))

        make_label(form, "Password", self.theme, size=10).grid(row=2, column=0, sticky="w")
        pw_row = tk.Frame(form, bg=self.theme["panel"])
        pw_row.grid(row=3, column=0, sticky="ew", pady=(6, 14))
        pw_row.columnconfigure(0, weight=1)
        self.pw_entry = make_entry(pw_row, self.theme, show="•")
        self.pw_entry.grid(row=0, column=0, sticky="ew")
        self.show_pw = tk.BooleanVar(value=False)
        def toggle_pw():
            self.pw_entry.configure(show="" if self.show_pw.get() else "•")
        tk.Checkbutton(pw_row, text="Show", variable=self.show_pw, command=toggle_pw,
                       bg=self.theme["panel"], fg=self.theme["muted"], selectcolor=self.theme["bg0"],
                       activebackground=self.theme["panel"], activeforeground=self.theme["text"]).grid(row=0, column=1, padx=10)

        make_label(form, "OTP", self.theme, size=10).grid(row=4, column=0, sticky="w")
        self.otp_entry = make_entry(form, self.theme)
        self.otp_entry.grid(row=5, column=0, sticky="ew", pady=(6, 6))

        self.status = make_label(panel, "", self.theme, size=10)
        self.status.pack(pady=(4, 8))

        btns = tk.Frame(panel, bg=self.theme["panel"])
        btns.pack(pady=10)

        self.login_btn = make_button(btns, "Request OTP", self.theme, self.request_otp)
        self.login_btn.grid(row=0, column=0, padx=10)

        self.verify_btn = make_button(btns, "Verify & Login", self.theme, self.verify_login)
        self.verify_btn.grid(row=0, column=1, padx=10)

        if self.on_register:
            label = "Register"
            reg_btn = make_button(btns, label, self.theme, self.on_register)
            reg_btn.grid(row=1, column=0, columnspan=2, pady=(10,0))

        topbar = tk.Frame(panel, bg=self.theme["panel"])
        topbar.place(x=0, y=0, relwidth=1, height=40)
        if self.on_back:
            back_btn = tk.Button(topbar, text="← Back", command=self.on_back, bg=self.theme["panel"], fg=self.theme["muted"], relief="flat")
            back_btn.pack(side="left", padx=10, pady=6)
        self.mode_btn = tk.Button(topbar, text="☾ / ☀", command=self.toggle_mode, bg=self.theme["panel"], fg=self.theme["muted"], relief="flat")
        self.mode_btn.pack(side="right", padx=10, pady=6)

        form.columnconfigure(0, weight=1)

        self._otp_token = None
        self._nonce = None

    def toggle_mode(self):
        # Persist the new preference on the root App and re-render via App navigation.
        try:
            if hasattr(self.master, "portal_dark_mode"):
                self.master.portal_dark_mode[self.portal_role] = not self.master.portal_dark_mode.get(self.portal_role, True)
            # Rebuild the screen through App so it is tracked and the old frame is destroyed.
            if hasattr(self.master, "show_login"):
                self.master.show_login(self.portal_role)
                return
        except Exception:
            pass
        # Fallback: no-op (prevents creating untracked frames)
        return

    def request_otp(self):
        try:
            api.health()
        except Exception:
            messagebox.showerror("Server/DB", "Server not reachable. Start MongoDB and run: python -m server.app")
            return
        username = self.user_entry.get().strip()
        password = self.pw_entry.get()

        # Client-side validation to prevent confusing 400s + accidental lockouts.
        if not username or not EMAIL_RE.match(username):
            self.status.config(text="Enter a valid email username.")
            messagebox.showerror("Login", "Please enter a valid email address for Username.")
            return
        if not password:
            self.status.config(text="Password is required.")
            messagebox.showerror("Login", "Password is required.")
            return

        try:
            resp = api.post("/auth/request-otp", {"username": username, "password": password})
            self._otp_token = resp["otp_token"]
            self._nonce = resp["nonce"]
            # Demo convenience: show OTP in a popup if the server returns it.
            otp_code = resp.get("otp_code")
            if otp_code:
                try:
                    self.otp_entry.delete(0, "end")
                    self.otp_entry.insert(0, otp_code)
                except Exception:
                    pass
                messagebox.showinfo("OTP", f"Your OTP is: {otp_code}\n\nValid for 2 minutes.")
                self.status.config(text="OTP issued. Enter OTP and click Verify & Login.")
            else:
                self.status.config(text="OTP requested. Check server terminal.")
        except api.APIError as e:
            self.status.config(text=str(e))
            messagebox.showerror("OTP Request Failed", str(e))

    def verify_login(self):
        if not self._otp_token or not self._nonce:
            self.status.config(text="Please request OTP first.")
            return
        username = self.user_entry.get().strip()
        password = self.pw_entry.get()
        otp = self.otp_entry.get().strip()
        try:
            p12 = keystore_path(username)
            sig_b64 = sign_text_p12(p12, password, self._nonce)
        except Exception as e:
            self.status.config(text=f"Keystore/sign error: {e}")
            return
        try:
            resp = api.post("/auth/verify", {"otp_token": self._otp_token, "otp_code": otp, "signature_b64": sig_b64})
            token = resp["access_token"]
            role = resp["role"]
            # enforce portal separation
            if self.portal_role == "admin" and role != "admin":
                self.status.config(text="This account is not an admin.")
                return
            self.on_login_success(token, role, username)
        except api.APIError as e:
            self.status.config(text=str(e))
            messagebox.showerror("Login Failed", str(e))
