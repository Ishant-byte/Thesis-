from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from client import api
import re

from client.ui.widgets.base import AnimatedBackground, make_button, make_label, make_entry, ScrollableFrame
from client.ui.themes.themes import USER_THEME, ADMIN_THEME

DEPARTMENTS = ["HR", "IT", "Finance", "Operations", "Sales", "Marketing", "Security"]

# Professional role titles shown during registration (requested).
ADMIN_ROLES = [
    "System Administrator",
    "Security Administrator",
    "HR Administrator",
    "Compliance Administrator",
]

EMPLOYEE_ROLES = [
    "HR Officer",
    "Recruitment Coordinator",
    "Payroll Specialist",
    "Finance Assistant",
    "IT Support Analyst",
    "Operations Coordinator",
]

EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


class RegisterScreen(tk.Frame):
    """Public registration screen.

    Creates a user + issues a certificate and PKCS#12 keystore on the server.

    Role is derived from which portal opened this screen (admin/employee).
    """

    def __init__(self, master, on_done, portal_role: str = "employee", on_login=None):
        super().__init__(master)
        self.on_done = on_done
        self.on_login = on_login
        self.portal_role = portal_role
        self.theme = ADMIN_THEME if portal_role == "admin" else USER_THEME
        self.pack(fill="both", expand=True)

        self.bg = AnimatedBackground(self, self.theme)
        self.bg.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.bg.start()

        panel = tk.Frame(self, bg=self.theme["panel"])
        panel.place(relx=0.5, rely=0.5, anchor="center", width=720, height=620)
        panel.grid_propagate(False)
        panel.rowconfigure(3, weight=1)
        panel.columnconfigure(0, weight=1)

        # Top bar: always-visible navigation
        topbar = tk.Frame(panel, bg=self.theme["panel"])
        topbar.grid(row=0, column=0, sticky="ew")
        tk.Button(
            topbar,
            text="← Back",
            command=self.on_done,
            bg=self.theme["panel"],
            fg=self.theme["muted"],
            relief="flat",
        ).pack(side="left", padx=10, pady=8)

        title = "Admin Registration" if portal_role == "admin" else "Employee Registration"
        make_label(panel, title, self.theme, size=20, bold=True).grid(row=1, column=0, pady=(6, 4))
        make_label(panel, "Create an account. Strong password required.", self.theme, size=11).grid(row=2, column=0, pady=(0, 10))

        # Scrollable form (prevents fields going off-screen)
        sc = ScrollableFrame(panel, bg=self.theme["panel"], width=650, height=420)
        sc.grid(row=3, column=0, padx=30, pady=(0, 8), sticky="nsew")

        form = tk.Frame(sc.inner, bg=self.theme["panel"])
        form.pack(pady=0, padx=10, fill="x")
        form.columnconfigure(0, weight=1)

        def add_field(label, row, show=None):
            make_label(form, label, self.theme, size=10).grid(row=row, column=0, sticky="w")
            e = make_entry(form, self.theme, show=show)
            e.grid(row=row + 1, column=0, sticky="ew", pady=(6, 14))
            return e

        self.user = add_field("Username (email)", 0)
        self.pw = add_field("Password (min 8, strong)", 2, show="•")
        self.pw2 = add_field("Confirm Password", 4, show="•")
        self.fn = add_field("First Name", 6)
        self.ln = add_field("Last Name", 8)

        # Job role dropdown (different lists for admin vs employee)
        make_label(form, "Role", self.theme, size=10).grid(row=10, column=0, sticky="w")
        role_list = ADMIN_ROLES if portal_role == "admin" else EMPLOYEE_ROLES
        self.job_role = tk.StringVar(value=role_list[0])
        role_opt = tk.OptionMenu(form, self.job_role, *role_list)
        role_opt.configure(bg=self.theme["bg0"], fg=self.theme["text"], relief="flat", highlightthickness=0)
        role_opt.grid(row=11, column=0, sticky="ew", pady=(6, 14))

        make_label(form, "Department", self.theme, size=10).grid(row=12, column=0, sticky="w")
        self.dept = tk.StringVar(value="Security" if portal_role == "admin" else DEPARTMENTS[0])
        opt = tk.OptionMenu(form, self.dept, *DEPARTMENTS)
        opt.configure(bg=self.theme["bg0"], fg=self.theme["text"], relief="flat", highlightthickness=0)
        opt.grid(row=13, column=0, sticky="ew", pady=(6, 14))

        self.phone = add_field("Phone (optional)", 14)

        self.status = make_label(panel, "", self.theme, size=10)
        self.status.grid(row=4, column=0, pady=(0, 6))

        # Footer buttons: always visible (fixes "missing submit/back" on smaller screens)
        btns = tk.Frame(panel, bg=self.theme["panel"])
        btns.grid(row=5, column=0, pady=(6, 14))
        make_button(btns, "Submit", self.theme, self.register).grid(row=0, column=0, padx=10)
        make_button(btns, "Back to Login", self.theme, (self.on_login or self.on_done)).grid(row=0, column=1, padx=10)

    def register(self):
        username = self.user.get().strip()
        pw = self.pw.get()

        if not username or not EMAIL_RE.match(username):
            self.status.config(text="Username must be a valid email.")
            return

        if pw != self.pw2.get():
            self.status.config(text="Passwords do not match.")
            return

        # Client-side password policy: mirrors server validation.
        if len(pw) < 8:
            self.status.config(text="Password must be at least 8 characters.")
            return
        if not re.search(r"[A-Z]", pw) or not re.search(r"[a-z]", pw) or not re.search(r"[0-9]", pw) or not re.search(r"[^A-Za-z0-9]", pw):
            self.status.config(text="Password must include upper, lower, number, and special character.")
            return
        try:
            api.health()
        except Exception:
            messagebox.showerror("Server/DB", "Server not reachable. Start MongoDB and run: python -m server.app")
            return

        payload = {
            "username": username,
            "password": pw,
            "first_name": self.fn.get().strip(),
            "last_name": self.ln.get().strip(),
            "job_role": self.job_role.get(),
            "department": self.dept.get(),
            "phone": self.phone.get().strip() or None,
            "role": "admin" if self.portal_role == "admin" else "employee",
        }

        try:
            api.post("/auth/register", payload)
            who = "Admin" if self.portal_role == "admin" else "Employee"
            messagebox.showinfo(
                "Registration",
                f"{who} registration successful.\n\nA PKCS#12 keystore was created at:\n  pki/users/<username>/keystore.p12\n\nUse your password to unlock it during login.",
            )
            self.on_done()
        except api.APIError as e:
            self.status.config(text=str(e))
            messagebox.showerror("Registration Failed", str(e))
