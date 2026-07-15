from __future__ import annotations
import tkinter as tk
from tkinter import messagebox
from client import api
from client.ui.widgets.base import make_label, make_entry, make_button

class LeaveTab(tk.Frame):
    def __init__(self, master, dashboard):
        super().__init__(master, bg=dashboard.theme["panel"])
        self.d = dashboard
        self.theme = dashboard.theme

        make_label(self, "Leave", self.theme, size=14, bold=True).pack(anchor="w", padx=12, pady=(12,6))

        if self.d.role != "admin":
            self._build_user()
        else:
            self._build_admin()

    def _build_user(self):
        form = tk.Frame(self, bg=self.theme["panel"])
        form.pack(fill="x", padx=12, pady=10)
        form.columnconfigure(1, weight=1)

        def row(label, r):
            make_label(form, label, self.theme, size=10).grid(row=r, column=0, sticky="w", pady=6)
            e = make_entry(form, self.theme)
            e.grid(row=r, column=1, sticky="ew", pady=6, padx=(10,0))
            return e

        self.typ = row("Type (e.g., Sick/Vacation)", 0)
        self.start = row("Start date (YYYY-MM-DD)", 1)
        self.end = row("End date (YYYY-MM-DD)", 2)
        self.reason = row("Reason", 3)

        btns = tk.Frame(self, bg=self.theme["panel"])
        btns.pack(anchor="w", padx=12, pady=(0,8))
        make_button(btns, "Submit Request", self.theme, self.submit).pack(side="left")
        make_button(btns, "Refresh", self.theme, self.refresh).pack(side="left", padx=10)

        wrap = tk.Frame(self, bg=self.theme["panel"])
        wrap.pack(fill="both", expand=True, padx=12, pady=12)
        self.list = tk.Listbox(wrap, bg=self.theme["bg0"], fg=self.theme["text"], highlightthickness=1, highlightbackground=self.theme["accent"])
        sb = tk.Scrollbar(wrap, orient="vertical", command=self.list.yview)
        self.list.configure(yscrollcommand=sb.set)
        self.list.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.refresh()

    def submit(self):
        try:
            api.post("/me/leave", {
                "leave_type": self.typ.get().strip(),
                "start_date": self.start.get().strip(),
                "end_date": self.end.get().strip(),
                "reason": self.reason.get().strip(),
            }, token=self.d.token)
            messagebox.showinfo("Leave", "Leave request submitted.")
            self.refresh()
        except api.APIError as e:
            messagebox.showerror("Leave", str(e))

    def refresh(self):
        self.list.delete(0,"end")
        try:
            data = api.get("/me/leave", token=self.d.token)
            for r in data.get("requests", []):
                self.list.insert("end", f"{r['status']:<9} {r['leave_type']} {r['start_date']}→{r['end_date']} (id={r['_id']})")
        except api.APIError as e:
            self.list.insert("end", str(e))

    def _build_admin(self):
        btns = tk.Frame(self, bg=self.theme["panel"])
        btns.pack(anchor="w", padx=12, pady=10)
        make_button(btns, "Refresh", self.theme, self.refresh_admin).pack(side="left")

        wrap = tk.Frame(self, bg=self.theme["panel"])
        wrap.pack(fill="both", expand=True, padx=12, pady=(0,12))
        self.list = tk.Listbox(wrap, bg=self.theme["bg0"], fg=self.theme["text"], highlightthickness=1, highlightbackground=self.theme["accent"])
        sb = tk.Scrollbar(wrap, orient="vertical", command=self.list.yview)
        self.list.configure(yscrollcommand=sb.set)
        self.list.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        act = tk.Frame(self, bg=self.theme["panel"])
        act.pack(fill="x", padx=12, pady=(0,12))
        make_label(act, "Selected leave_id:", self.theme, size=10).pack(side="left")
        self.sel = make_entry(act, self.theme)
        self.sel.pack(side="left", fill="x", expand=True, padx=10)
        make_button(act, "Approve", self.theme, lambda: self.decide("approve")).pack(side="left", padx=6)
        make_button(act, "Reject", self.theme, lambda: self.decide("reject")).pack(side="left")

        self.list.bind("<<ListboxSelect>>", self.on_select)
        self.refresh_admin()

    def refresh_admin(self):
        self.list.delete(0,"end")
        try:
            data = api.get("/admin/leave", token=self.d.token)
            for r in data.get("requests", []):
                self.list.insert("end", f"{r['status']:<9} {r['username']} {r['leave_type']} {r['start_date']}→{r['end_date']} (id={r['_id']})")
        except api.APIError as e:
            self.list.insert("end", str(e))

    def on_select(self, _):
        sel = self.list.curselection()
        if not sel:
            return
        line = self.list.get(sel[0])
        # parse id=...
        if "id=" in line:
            leave_id = line.split("id=")[-1].strip(")")
            self.sel.delete(0,"end"); self.sel.insert(0, leave_id)

    def decide(self, decision: str):
        leave_id = self.sel.get().strip()
        if not leave_id:
            return
        try:
            api.post(f"/admin/leave/{leave_id}", {"decision": decision}, token=self.d.token)
            self.refresh_admin()
        except api.APIError as e:
            messagebox.showerror("Leave", str(e))
