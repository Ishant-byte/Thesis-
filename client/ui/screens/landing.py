from __future__ import annotations

import tkinter as tk

from client.ui.themes.themes import ADMIN_THEME, USER_THEME
from client.ui.widgets.base import AnimatedBackground, make_button, make_label
from client.ui.app_config import APP_NAME, TAGLINE, LOGO_PATH

class LandingScreen(tk.Frame):
    def __init__(self, master, on_choose):
        super().__init__(master)
        self.on_choose = on_choose
        self.pack(fill="both", expand=True)

        self.bg = AnimatedBackground(self, ADMIN_THEME)
        self.bg.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.bg.start()

        # Keep the landing panel tall enough so the logo cannot push the
        # portal buttons off-screen on smaller displays.
        panel = tk.Frame(self, bg=ADMIN_THEME["panel"])
        panel.place(relx=0.5, rely=0.5, anchor="center", width=560, height=420)

        # Branding
        self._logo_img = None
        try:
            # Downscale to avoid UI overflow (Tkinter does not auto-scale images).
            img = tk.PhotoImage(file=str(LOGO_PATH))
            # 256px -> 128px
            self._logo_img = img.subsample(2, 2)
            tk.Label(panel, image=self._logo_img, bg=ADMIN_THEME["panel"]).pack(pady=(20, 8))
        except Exception:
            pass

        title = make_label(panel, APP_NAME, ADMIN_THEME, size=24, bold=True)
        title.pack(pady=(0, 6))
        subtitle = make_label(panel, TAGLINE, ADMIN_THEME, size=11, bold=False)
        subtitle.pack(pady=(0, 14))

        btn_row = tk.Frame(panel, bg=ADMIN_THEME["panel"])
        btn_row.pack(pady=10)

        admin_btn = make_button(btn_row, "Admin Portal", ADMIN_THEME, lambda: self.on_choose("admin"))
        admin_btn.grid(row=0, column=0, padx=10)
        user_btn = make_button(btn_row, "Employee Portal", USER_THEME, lambda: self.on_choose("employee"))
        user_btn.grid(row=0, column=1, padx=10)
        # No noisy tips on landing. Errors are shown contextually on Login/Register.
