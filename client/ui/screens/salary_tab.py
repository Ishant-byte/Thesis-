from __future__ import annotations
import tkinter as tk
from tkinter import messagebox, simpledialog
from client import api
from client.ui.widgets.base import make_label, make_entry, make_button

class SalaryTab(tk.Frame):
    def __init__(self, master, dashboard):
        super().__init__(master, bg=dashboard.theme["panel"])
        self.d = dashboard
        self.theme = dashboard.theme
        make_label(self, "Salary / Payslips", self.theme, size=14, bold=True).pack(anchor="w", padx=12, pady=(12,6))

        top = tk.Frame(self, bg=self.theme["panel"])
        top.pack(fill="x", padx=12, pady=10)

        if self.d.role == "admin":
            make_label(top, "Target user:", self.theme, size=10).pack(side="left")
            self.target = make_entry(top, self.theme)
            self.target.pack(side="left", fill="x", expand=True, padx=10)
            make_button(top, "Add Record", self.theme, self.add_record).pack(side="left", padx=6)
            make_button(top, "Refresh", self.theme, self.refresh_admin).pack(side="left")
        else:
            make_button(top, "Refresh", self.theme, self.refresh_user).pack(side="left")

        wrap = tk.Frame(self, bg=self.theme["panel"])
        wrap.pack(fill="both", expand=True, padx=12, pady=12)
        self.box = tk.Listbox(wrap, bg=self.theme["bg0"], fg=self.theme["text"], highlightthickness=1, highlightbackground=self.theme["accent"])
        sb = tk.Scrollbar(wrap, orient="vertical", command=self.box.yview)
        self.box.configure(yscrollcommand=sb.set)
        self.box.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        if self.d.role == "admin":
            self.refresh_admin()
        else:
            self.refresh_user()

    def add_record(self):
        username = self.target.get().strip()
        if not username:
            return
        month = simpledialog.askstring("Salary", "Month (YYYY-MM):")
        if not month:
            return
        amount = simpledialog.askfloat("Salary", "Amount:")
        if amount is None:
            return
        note = simpledialog.askstring("Salary", "Note (optional):")
        try:
            api.post(f"/admin/salary/{username}", {"month": month, "amount": amount, "note": note}, token=self.d.token)
            messagebox.showinfo("Salary", "Record added.")
            self.refresh_admin()
        except api.APIError as e:
            messagebox.showerror("Salary", str(e))

    def refresh_admin(self):
        self.box.delete(0,"end")
        username = self.target.get().strip()
        if not username:
            self.box.insert("end", "Enter a target user to view records.")
            return
        try:
            data = api.get(f"/admin/salary/{username}", token=self.d.token)
            for r in data.get("records", []):
                self.box.insert("end", f"{r['month']}  amount={r['amount']}  note={r.get('note','')}  (created {r['created_at']})")
        except api.APIError as e:
            self.box.insert("end", str(e))

    def refresh_user(self):
        self.box.delete(0,"end")
        try:
            data = api.get("/me/salary", token=self.d.token)
            for r in data.get("records", []):
                self.box.insert("end", f"{r['month']}  amount={r['amount']}  note={r.get('note','')}  (created {r['created_at']})")
        except api.APIError as e:
            self.box.insert("end", str(e))
