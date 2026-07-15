from __future__ import annotations
import base64
import hashlib
import io
import json
import os
import zipfile
import tkinter as tk
from tkinter import filedialog, messagebox

from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography import x509

from client import api
from client.ui.widgets.base import make_label, make_button
from client.ui.app_config import project_root

def default_keystore_path(username: str) -> str:
    # Robust path resolution regardless of current working directory.
    root = project_root()
    return str(root / "pki" / "users" / username / "keystore.p12")

def sha256_file(path: str) -> bytes:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024*1024), b""):
            h.update(chunk)
    return h.digest()

class DocumentsTab(tk.Frame):
    def __init__(self, master, dashboard):
        super().__init__(master, bg=dashboard.theme["panel"])
        self.d = dashboard
        self.theme = dashboard.theme

        make_label(self, "Documents: Sign & Verify", self.theme, size=14, bold=True).pack(anchor="w", padx=12, pady=(12,6))

        box = tk.Frame(self, bg=self.theme["panel"])
        box.pack(fill="x", padx=12, pady=10)

        make_button(box, "Browse File to Sign", self.theme, self.pick_sign).pack(side="left")
        make_button(box, "Export Signature Bundle (ZIP)", self.theme, self.export_bundle).pack(side="left", padx=10)

        self.sign_file = None
        self.bundle = None

        make_label(self, "Verification", self.theme, size=12, bold=True).pack(anchor="w", padx=12, pady=(14,6))
        vbox = tk.Frame(self, bg=self.theme["panel"])
        vbox.pack(fill="x", padx=12, pady=10)
        make_button(vbox, "Choose File", self.theme, self.pick_verify_file).pack(side="left")
        make_button(vbox, "Choose Bundle ZIP", self.theme, self.pick_verify_bundle).pack(side="left", padx=10)
        make_button(vbox, "Verify", self.theme, self.verify).pack(side="left", padx=10)

        self.v_file = None
        self.v_bundle = None

        out_wrap = tk.Frame(self, bg=self.theme["panel"])
        out_wrap.pack(fill="both", expand=True, padx=12, pady=12)
        self.out = tk.Text(out_wrap, bg=self.theme["bg0"], fg=self.theme["text"], insertbackground=self.theme["text"], relief="flat", height=14)
        sb = tk.Scrollbar(out_wrap, orient="vertical", command=self.out.yview)
        self.out.configure(yscrollcommand=sb.set)
        self.out.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

    def log(self, s: str):
        self.out.insert("end", s + "\n")
        self.out.see("end")

    def pick_sign(self):
        fp = filedialog.askopenfilename(title="Select file to sign")
        if fp:
            self.sign_file = fp
            self.log(f"[sign] Selected: {fp}")

    def _prompt_password(self) -> str:
        import tkinter.simpledialog as sd
        pw = sd.askstring("Keystore Password", "Enter your password to unlock your keystore:", show="•")
        if not pw:
            raise ValueError("Password required")
        return pw

    def export_bundle(self):
        if not self.sign_file:
            messagebox.showerror("Sign", "Choose a file first.")
            return
        try:
            ca = api.get("/pki/ca.pem")["ca_cert_pem"]
            crl = api.get("/pki/crl.json")["revoked_serials"]
        except Exception as e:
            messagebox.showerror("Server", f"Cannot load CA/CRL: {e}")
            return

        pw = self._prompt_password()
        p12_path = default_keystore_path(self.d.username)
        try:
            key, cert, cas = pkcs12.load_key_and_certificates(open(p12_path,"rb").read(), pw.encode("utf-8"))
            if key is None or cert is None:
                raise ValueError("Invalid keystore")
            digest = sha256_file(self.sign_file)
            sig = key.sign(
                digest,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            bundle = {
                "v": 1,
                "alg": "RSA-PSS-SHA256",
                "hash_alg": "SHA256",
                "file_name": os.path.basename(self.sign_file),
                "sha256_b64": base64.b64encode(digest).decode("utf-8"),
                "signature_b64": base64.b64encode(sig).decode("utf-8"),
                "cert_pem": cert.public_bytes(serialization.Encoding.PEM).decode("utf-8"),
                "ca_cert_pem": ca,
                "meta": {
                    "signed_by": self.d.username,
                    # Store as string to avoid 64-bit integer limits in some stores.
                    "cert_serial": str(cert.serial_number),
                    "timestamp_utc": api.health()["time"],
                }
            }
            self.bundle = bundle
        except Exception as e:
            messagebox.showerror("Sign", str(e))
            return

        outzip = filedialog.asksaveasfilename(title="Save bundle ZIP", defaultextension=".zip", filetypes=[("ZIP","*.zip")])
        if not outzip:
            return
        try:
            with zipfile.ZipFile(outzip, "w", compression=zipfile.ZIP_DEFLATED) as z:
                z.writestr("bundle.json", json.dumps(self.bundle, indent=2))
                z.writestr("document.sha256", base64.b64decode(self.bundle["sha256_b64"]))
                z.writestr("signature.sig", base64.b64decode(self.bundle["signature_b64"]))
                z.writestr("signer_cert.pem", self.bundle["cert_pem"].encode("utf-8"))
                z.writestr("ca_cert.pem", self.bundle["ca_cert_pem"].encode("utf-8"))
            self.log(f"[sign] Bundle exported: {outzip}")
            self.log("[sign] Included: bundle.json, signer_cert.pem, ca_cert.pem, signature.sig, document.sha256")
        except Exception as e:
            messagebox.showerror("Export", str(e))

    def pick_verify_file(self):
        fp = filedialog.askopenfilename(title="Select file to verify")
        if fp:
            self.v_file = fp
            self.log(f"[verify] File: {fp}")

    def pick_verify_bundle(self):
        fp = filedialog.askopenfilename(title="Select bundle ZIP", filetypes=[("ZIP","*.zip")])
        if fp:
            self.v_bundle = fp
            self.log(f"[verify] Bundle: {fp}")

    def verify(self):
        if not self.v_file or not self.v_bundle:
            messagebox.showerror("Verify", "Choose file and bundle ZIP.")
            return
        try:
            ca_server = api.get("/pki/ca.pem")["ca_cert_pem"]
            revoked = set(str(x) for x in api.get("/pki/crl.json")["revoked_serials"])
        except Exception as e:
            messagebox.showerror("Server", f"Cannot load CA/CRL: {e}")
            return
        try:
            with zipfile.ZipFile(self.v_bundle, "r") as z:
                bundle = json.loads(z.read("bundle.json").decode("utf-8"))
            digest = sha256_file(self.v_file)
            if digest != base64.b64decode(bundle["sha256_b64"]):
                self.log("[FAIL] Hash mismatch. The file has changed or wrong file selected.")
                return
            cert = x509.load_pem_x509_certificate(bundle["cert_pem"].encode("utf-8"))
            # CA pin check
            if bundle["ca_cert_pem"].strip() != ca_server.strip():
                self.log("[FAIL] CA certificate mismatch (CA pinning failed).")
                return
            if str(cert.serial_number) in revoked:
                self.log("[FAIL] Certificate is revoked (CRL).")
                return
            sig = base64.b64decode(bundle["signature_b64"])
            cert.public_key().verify(
                sig,
                digest,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            self.log("[OK] Signature verified.")
            self.log(f"     Signed by: {bundle['meta'].get('signed_by')}")
            self.log(f"     Serial: {bundle['meta'].get('cert_serial')}")
            self.log(f"     Algorithms: {bundle['alg']} + {bundle['hash_alg']}")
        except Exception as e:
            self.log(f"[FAIL] Verification error: {e}")
