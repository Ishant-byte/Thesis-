from __future__ import annotations

import tkinter as tk

from client.ui.themes.themes import ADMIN_THEME, USER_THEME
from client.ui.widgets.base import AnimatedBackground, make_button, make_label
from client.ui.app_config import APP_NAME


class PortalMenuScreen(tk.Frame):
    """Portal selection -> Login/Register chooser.

    The user explicitly asked for a screen that appears after selecting
    Admin/Employee portal, offering *both* Login and Register actions.
    """

    def __init__(
        self,
        master,
        portal_role: str,
        on_login,
        on_register,
        on_back,
    ):
        super().__init__(master)
        self.portal_role = portal_role
        self.on_login = on_login
        self.on_register = on_register
        self.on_back = on_back

        self.theme = ADMIN_THEME if portal_role == "admin" else USER_THEME
        self.pack(fill="both", expand=True)

        self.bg = AnimatedBackground(self, self.theme)
        self.bg.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.bg.start()

        panel = tk.Frame(self, bg=self.theme["panel"])
        panel.place(relx=0.5, rely=0.5, anchor="center", width=560, height=360)

        make_label(panel, APP_NAME, self.theme, size=18, bold=True).pack(pady=(28, 6))
        title = "Admin Portal" if portal_role == "admin" else "Employee Portal"
        make_label(panel, title, self.theme, size=14, bold=True).pack(pady=(0, 10))
        make_label(panel, "Choose an action", self.theme, size=11).pack(pady=(0, 18))

        btns = tk.Frame(panel, bg=self.theme["panel"])
        btns.pack(pady=10)
        make_button(btns, "Login", self.theme, self.on_login).grid(row=0, column=0, padx=10)
        make_button(btns, "Register", self.theme, self.on_register).grid(row=0, column=1, padx=10)

        # Top bar: back + mode toggle consistent with other screens
        topbar = tk.Frame(panel, bg=self.theme["panel"])
        topbar.place(x=0, y=0, relwidth=1, height=40)
        tk.Button(
            topbar,
            text="← Back",
            command=self.on_back,
            bg=self.theme["panel"],
            fg=self.theme["muted"],
            relief="flat",
        ).pack(side="left", padx=10, pady=6)
