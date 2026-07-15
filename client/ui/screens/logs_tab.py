from __future__ import annotations
import tkinter as tk
from tkinter import messagebox, filedialog
from client import api
from client.ui.widgets.base import make_label, make_entry, make_button

class LogsTab(tk.Frame):
    def __init__(self, master, dashboard):
        super().__init__(master, bg=dashboard.theme["panel"])
        self.d = dashboard
        self.theme = dashboard.theme

        make_label(self, "Logs", self.theme, size=14, bold=True).pack(anchor="w", padx=12, pady=(12,6))

        if self.d.role == "admin":
            self._build_admin()
        else:
            self._build_user()

    def _build_user(self):
        btns = tk.Frame(self, bg=self.theme["panel"])
        btns.pack(anchor="w", padx=12, pady=10)
        make_button(btns, "Refresh", self.theme, self.refresh_user).pack(side="left")

        wrap = tk.Frame(self, bg=self.theme["panel"])
        wrap.pack(fill="both", expand=True, padx=12, pady=12)
        self.box = tk.Text(wrap, bg=self.theme["bg0"], fg=self.theme["text"], insertbackground=self.theme["text"], relief="flat")
        sb = tk.Scrollbar(wrap, orient="vertical", command=self.box.yview)
        self.box.configure(yscrollcommand=sb.set)
        self.box.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.refresh_user()

    def refresh_user(self):
        self.box.delete("1.0","end")
        try:
            data = api.get("/me/logs", token=self.d.token)
            for r in data.get("logs", []):
                self.box.insert("end", f"{r['timestamp']} {r['severity']} {r['event_type']} {r.get('message','')}\n")
        except api.APIError as e:
            self.box.insert("end", str(e))

    def _build_admin(self):
        filt = tk.Frame(self, bg=self.theme["panel"])
        filt.pack(fill="x", padx=12, pady=10)
        filt.columnconfigure(1, weight=1)
        filt.columnconfigure(3, weight=1)

        def field(label, c, r):
            make_label(filt, label, self.theme, size=10).grid(row=r, column=c, sticky="w", padx=(0,6), pady=4)
            e = make_entry(filt, self.theme)
            e.grid(row=r, column=c+1, sticky="ew", padx=(0,10), pady=4)
            return e

        self.actor = field("Actor", 0, 0)
        self.target = field("Target", 2, 0)
        self.event = field("Event type", 0, 1)
        self.start = field("Start (ISO, optional)", 2, 1)
        self.end = field("End (ISO, optional)", 0, 2)

        btns = tk.Frame(self, bg=self.theme["panel"])
        btns.pack(anchor="w", padx=12, pady=(0,8))
        make_button(btns, "Search", self.theme, self.search_admin).pack(side="left")
        make_button(btns, "Export CSV", self.theme, self.export_admin).pack(side="left", padx=10)

        wrap = tk.Frame(self, bg=self.theme["panel"])
        wrap.pack(fill="both", expand=True, padx=12, pady=12)
        self.box = tk.Text(wrap, bg=self.theme["bg0"], fg=self.theme["text"], insertbackground=self.theme["text"], relief="flat")
        sb = tk.Scrollbar(wrap, orient="vertical", command=self.box.yview)
        self.box.configure(yscrollcommand=sb.set)
        self.box.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.search_admin()

    def _params(self):
        p = {}
        if self.actor.get().strip(): p["actor"] = self.actor.get().strip()
        if self.target.get().strip(): p["target"] = self.target.get().strip()
        if self.event.get().strip(): p["event_type"] = self.event.get().strip()
        if self.start.get().strip(): p["start"] = self.start.get().strip()
        if self.end.get().strip(): p["end"] = self.end.get().strip()
        return p

    def search_admin(self):
        self.box.delete("1.0","end")
        try:
            data = api.get("/admin/logs", token=self.d.token, params=self._params())
            for r in data.get("logs", []):
                self.box.insert("end", f"{r['timestamp']} {r['severity']} {r['event_type']} actor={r.get('actor_username')} target={r.get('target_username')} {r.get('message','')}\n")
        except api.APIError as e:
            self.box.insert("end", str(e))

    def export_admin(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV","*.csv")])
        if not path:
            return
        try:
            import requests, os
            from client.api import BASE
            headers = {"Authorization": f"Bearer {self.d.token}"}
            r = requests.get(f"{BASE}/admin/logs/export", headers=headers, params=self._params(), timeout=20)
            if r.status_code >= 400:
                raise Exception(r.text)
            with open(path, "wb") as f:
                f.write(r.content)
            messagebox.showinfo("Export", f"Saved: {path}")
        except Exception as e:
            messagebox.showerror("Export", str(e))
