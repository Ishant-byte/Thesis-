from __future__ import annotations
import tkinter as tk
from tkinter import messagebox, simpledialog
from client import api
from client.ui.widgets.base import make_label, make_entry, make_button

DEPARTMENTS = ["HR","IT","Finance","Operations","Sales","Marketing","Security"]

class EmployeesTab(tk.Frame):
    def __init__(self, master, dashboard):
        super().__init__(master, bg=dashboard.theme["panel"])
        self.d = dashboard
        self.theme = dashboard.theme

        make_label(self, "Employees & Admins", self.theme, size=14, bold=True).pack(anchor="w", padx=12, pady=(12,6))

        top = tk.Frame(self, bg=self.theme["panel"])
        top.pack(fill="x", padx=12, pady=10)
        make_button(top, "Refresh", self.theme, self.refresh).pack(side="left")
        make_button(top, "Create User", self.theme, self.create_user).pack(side="left", padx=10)

        # Scrollable list (some orgs have many users).
        list_wrap = tk.Frame(self, bg=self.theme["panel"])
        list_wrap.pack(fill="x", padx=12, pady=(0, 10))
        self.list = tk.Listbox(
            list_wrap,
            bg=self.theme["bg0"],
            fg=self.theme["text"],
            height=12,
            highlightthickness=1,
            highlightbackground=self.theme["accent"],
        )
        sb = tk.Scrollbar(list_wrap, orient="vertical", command=self.list.yview)
        self.list.configure(yscrollcommand=sb.set)
        self.list.pack(side="left", fill="x", expand=True)
        sb.pack(side="right", fill="y")
        self.list.bind("<<ListboxSelect>>", self.on_select)

        act = tk.Frame(self, bg=self.theme["panel"])
        act.pack(fill="x", padx=12, pady=(0,10))
        make_label(act, "Selected username:", self.theme, size=10).pack(side="left")
        self.sel = make_entry(act, self.theme)
        self.sel.pack(side="left", fill="x", expand=True, padx=10)

        make_button(act, "Delete", self.theme, self.delete_user).pack(side="left", padx=6)
        make_button(act, "Revoke Cert", self.theme, self.revoke).pack(side="left", padx=6)
        make_button(act, "Rotate Cert", self.theme, self.rotate).pack(side="left", padx=6)

        self.info = make_label(self, "", self.theme, size=10)
        self.info.pack(anchor="w", padx=12)

        self.refresh()

    def refresh(self):
        self.list.delete(0,"end")
        try:
            data = api.get("/admin/users", token=self.d.token)
            self._users = data.get("users", [])
            for u in self._users:
                self.list.insert("end", f"{u['role']:<8} {u.get('presence_state','offline'):<7} {u['username']}")
        except api.APIError as e:
            self.list.insert("end", str(e))

    def on_select(self, _):
        sel = self.list.curselection()
        if not sel:
            return
        line = self.list.get(sel[0])
        username = line.split()[-1]
        self.sel.delete(0,"end"); self.sel.insert(0, username)

    def create_user(self):
        # Minimal dialog-based creation
        username = simpledialog.askstring("Create user", "Username (email):")
        if not username: return
        password = simpledialog.askstring("Create user", "Temporary password (strong):", show="•")
        if not password: return
        first = simpledialog.askstring("Create user", "First name:") or ""
        last = simpledialog.askstring("Create user", "Last name:") or ""
        dept = simpledialog.askstring("Create user", f"Department {DEPARTMENTS}:") or "HR"
        role = simpledialog.askstring("Create user", "Role (employee/admin):") or "employee"
        phone = simpledialog.askstring("Create user", "Phone (optional):")
        try:
            api.post("/admin/users/create", {
                "username": username.strip(),
                "password": password,
                "first_name": first.strip(),
                "last_name": last.strip(),
                "department": dept.strip(),
                "phone": phone.strip() if phone else None,
                "role": role.strip(),
            }, token=self.d.token)
            messagebox.showinfo("Create user", "User created. Keystore saved under pki/users/<username>/keystore.p12")
            self.refresh()
        except api.APIError as e:
            messagebox.showerror("Create user", str(e))

    def delete_user(self):
        username = self.sel.get().strip()
        if not username:
            return
        if messagebox.askyesno("Delete", f"Delete {username}?"):
            try:
                import requests
                from client.api import BASE
                headers = {"Authorization": f"Bearer {self.d.token}"}
                r = requests.delete(f"{BASE}/admin/users/{username}", headers=headers, timeout=10)
                if r.status_code >= 400:
                    raise Exception(r.text)
                self.refresh()
            except Exception as e:
                messagebox.showerror("Delete", str(e))

    def revoke(self):
        username = self.sel.get().strip()
        if not username:
            return
        reason = simpledialog.askstring("Revoke cert", "Reason:", initialvalue="compromised") or "unspecified"
        try:
            api.post(f"/admin/users/{username}/revoke-cert", {"reason": reason}, token=self.d.token)
            messagebox.showinfo("Revoke", "Certificate revoked.")
        except api.APIError as e:
            messagebox.showerror("Revoke", str(e))

    def rotate(self):
        username = self.sel.get().strip()
        if not username:
            return
        new_pw = simpledialog.askstring("Rotate cert", "New keystore password (strong):", show="•")
        if not new_pw:
            return
        try:
            resp = api.post(f"/admin/users/{username}/rotate-cert", {"new_password": new_pw}, token=self.d.token)
            messagebox.showinfo("Rotate", f"Rotated. New keystore path:\n{resp['pkcs12_path']}")
        except api.APIError as e:
            messagebox.showerror("Rotate", str(e))
