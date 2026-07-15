from __future__ import annotations
import tkinter as tk
from tkinter import messagebox
from client import api
from client.ui.widgets.base import make_label, make_entry, make_button

class NoticesTab(tk.Frame):
    def __init__(self, master, dashboard):
        super().__init__(master, bg=dashboard.theme["panel"])
        self.d = dashboard
        self.theme = dashboard.theme

        make_label(self, "Notices", self.theme, size=14, bold=True).pack(anchor="w", padx=12, pady=(12,6))

        if self.d.role == "admin":
            form = tk.Frame(self, bg=self.theme["panel"])
            form.pack(fill="x", padx=12, pady=10)
            form.columnconfigure(1, weight=1)
            make_label(form, "Title", self.theme, size=10).grid(row=0, column=0, sticky="w", pady=6)
            self.title = make_entry(form, self.theme)
            self.title.grid(row=0, column=1, sticky="ew", pady=6, padx=(10,0))
            make_label(form, "Body", self.theme, size=10).grid(row=1, column=0, sticky="w", pady=6)
            body_wrap = tk.Frame(form, bg=self.theme["panel"])
            body_wrap.grid(row=1, column=1, sticky="ew", pady=6, padx=(10,0))
            self.body = tk.Text(body_wrap, height=4, bg=self.theme["bg0"], fg=self.theme["text"], insertbackground=self.theme["text"], relief="flat")
            sb = tk.Scrollbar(body_wrap, orient="vertical", command=self.body.yview)
            self.body.configure(yscrollcommand=sb.set)
            self.body.pack(side="left", fill="both", expand=True)
            sb.pack(side="right", fill="y")
            make_button(form, "Post", self.theme, self.post).grid(row=2, column=1, sticky="e", pady=8)

        btns = tk.Frame(self, bg=self.theme["panel"])
        btns.pack(anchor="w", padx=12, pady=(0,8))
        make_button(btns, "Refresh", self.theme, self.refresh).pack(side="left")

        list_wrap = tk.Frame(self, bg=self.theme["panel"])
        list_wrap.pack(fill="both", expand=True, padx=12, pady=12)
        self.list = tk.Listbox(list_wrap, bg=self.theme["bg0"], fg=self.theme["text"], highlightthickness=1, highlightbackground=self.theme["accent"])
        sb = tk.Scrollbar(list_wrap, orient="vertical", command=self.list.yview)
        self.list.configure(yscrollcommand=sb.set)
        self.list.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self.refresh()

    def refresh(self):
        self.list.delete(0,"end")
        try:
            data = api.get("/notices", token=self.d.token)
            for n in data.get("notices", []):
                self.list.insert("end", f"{n['created_at']} • {n['title']} (by {n['created_by']})")
                for line in n["body"].splitlines():
                    self.list.insert("end", f"    {line}")
                self.list.insert("end", "")
        except api.APIError as e:
            self.list.insert("end", str(e))

    def post(self):
        try:
            api.post("/admin/notices", {"title": self.title.get().strip(), "body": self.body.get("1.0","end").strip()}, token=self.d.token)
            self.title.delete(0,"end")
            self.body.delete("1.0","end")
            self.refresh()
        except api.APIError as e:
            messagebox.showerror("Notices", str(e))
