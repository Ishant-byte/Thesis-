from __future__ import annotations
import tkinter as tk
from tkinter import messagebox
from client import api
from client.ui.widgets.base import AnimatedBackground, make_button, make_label, make_entry
from client.ui.themes.themes import USER_THEME, ADMIN_THEME
DEPARTMENTS = ["HR","IT","Finance","Operations","Sales","Marketing","Security"]

class EnrollScreen(tk.Frame):
    def __init__(self, master, on_done, portal_role: str = "employee"):
        super().__init__(master)
        self.on_done = on_done
        self.portal_role = portal_role
        self.theme = ADMIN_THEME if portal_role == "admin" else USER_THEME
        self.pack(fill="both", expand=True)

        self.bg = AnimatedBackground(self, self.theme)
        self.bg.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.bg.start()

        panel = tk.Frame(self, bg=self.theme["panel"])
        panel.place(relx=0.5, rely=0.5, anchor="center", width=620, height=520)

        title = "Admin Registration" if portal_role == "admin" else "Employee Registration"
        make_label(panel, title, self.theme, size=20, bold=True).pack(pady=(24,6))
        make_label(panel, "Use the Invite Code provided by an Admin", self.theme, size=11).pack(pady=(0,16))

        form = tk.Frame(panel, bg=self.theme["panel"])
        form.pack(pady=10, padx=40, fill="x")
        form.columnconfigure(0, weight=1)

        def add_field(label, row, show=None):
            make_label(form, label, self.theme, size=10).grid(row=row, column=0, sticky="w")
            e = make_entry(form, self.theme, show=show)
            e.grid(row=row+1, column=0, sticky="ew", pady=(6,14))
            return e

        self.inv = add_field("Invite Code", 0)
        self.user = add_field("Username (email)", 2)
        self.pw = add_field("Password (min 8, strong)", 4, show="•")
        self.pw2 = add_field("Confirm Password", 6, show="•")
        self.fn = add_field("First Name", 8)
        self.ln = add_field("Last Name", 10)

        make_label(form, "Department", self.theme, size=10).grid(row=12, column=0, sticky="w")
        self.dept = tk.StringVar(value=DEPARTMENTS[0])
        opt = tk.OptionMenu(form, self.dept, *DEPARTMENTS)
        opt.configure(bg=self.theme["bg0"], fg=self.theme["text"], relief="flat", highlightthickness=0)
        opt.grid(row=13, column=0, sticky="ew", pady=(6,14))

        self.phone = add_field("Phone (optional)", 14)

        self.status = make_label(panel, "", self.theme, size=10)
        self.status.pack(pady=(0,8))

        btns = tk.Frame(panel, bg=self.theme["panel"])
        btns.pack(pady=10)
        make_button(btns, "Register", self.theme, self.enroll).grid(row=0, column=0, padx=10)
        make_button(btns, "Back", self.theme, self.on_done).grid(row=0, column=1, padx=10)

    def enroll(self):
        if self.pw.get() != self.pw2.get():
            self.status.config(text="Passwords do not match.")
            return
        try:
            api.health()
        except Exception:
            messagebox.showerror("Server/DB", "Server not reachable. Start MongoDB and run: python -m server.app")
            return
        try:
            api.post("/auth/enroll", {
                "invite_code": self.inv.get().strip(),
                "username": self.user.get().strip(),
                "password": self.pw.get(),
                "first_name": self.fn.get().strip(),
                "last_name": self.ln.get().strip(),
                "department": self.dept.get(),
                "phone": self.phone.get().strip() or None,
            })
            who = "Admin" if self.portal_role == "admin" else "Employee"
            messagebox.showinfo("Registration", f"{who} registration successful.\nYour keystore is saved in pki/users/<username>/keystore.p12")
            self.on_done()
        except api.APIError as e:
            self.status.config(text=str(e))
