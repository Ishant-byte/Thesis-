from __future__ import annotations
import tkinter as tk
from tkinter import messagebox
from client import api
from client.ui.widgets.base import make_label, make_entry, make_button

class ProfileTab(tk.Frame):
    def __init__(self, master, dashboard):
        super().__init__(master, bg=dashboard.theme["panel"])
        self.d = dashboard
        self.theme = dashboard.theme

        make_label(self, "Profile", self.theme, size=14, bold=True).pack(anchor="w", padx=12, pady=(12,6))
        self.status = make_label(self, "", self.theme, size=10)
        self.status.pack(anchor="w", padx=12)

        form = tk.Frame(self, bg=self.theme["panel"])
        form.pack(fill="x", padx=12, pady=12)
        form.columnconfigure(1, weight=1)

        def row(label, r, show=None):
            make_label(form, label, self.theme, size=10).grid(row=r, column=0, sticky="w", pady=6)
            e = make_entry(form, self.theme, show=show)
            e.grid(row=r, column=1, sticky="ew", pady=6, padx=(10,0))
            return e

        self.fn = row("First name", 0)
        self.ln = row("Last name", 1)
        self.dept = row("Department", 2)
        self.phone = row("Phone", 3)
        self.addr = row("Address", 4)

        btns = tk.Frame(self, bg=self.theme["panel"])
        btns.pack(fill="x", padx=12, pady=(0,12))
        make_button(btns, "Refresh", self.theme, self.load).pack(side="left")
        make_button(btns, "Save", self.theme, self.save).pack(side="left", padx=10)

        self.load()

    def load(self):
        try:
            prof = api.get("/me/profile", token=self.d.token)
            self.fn.delete(0,"end"); self.fn.insert(0, prof.get("first_name",""))
            self.ln.delete(0,"end"); self.ln.insert(0, prof.get("last_name",""))
            self.dept.delete(0,"end"); self.dept.insert(0, prof.get("department",""))
            self.phone.delete(0,"end"); self.phone.insert(0, prof.get("phone",""))
            self.addr.delete(0,"end"); self.addr.insert(0, prof.get("address",""))
            self.status.config(text="Loaded.")
        except api.APIError as e:
            self.status.config(text=str(e))

    def save(self):
        try:
            api.put("/me/profile", {
                "first_name": self.fn.get().strip(),
                "last_name": self.ln.get().strip(),
                "department": self.dept.get().strip(),
                "phone": self.phone.get().strip(),
                "address": self.addr.get().strip(),
            }, token=self.d.token)
            self.status.config(text="Saved.")
        except api.APIError as e:
            self.status.config(text=str(e))
