from __future__ import annotations

import tkinter as tk

from client.ui.screens.landing import LandingScreen
from client.ui.screens.login import LoginScreen
from client.ui.screens.register import RegisterScreen
from client.ui.screens.portal_menu import PortalMenuScreen
from client.ui.screens.dashboard_admin import AdminDashboard
from client.ui.screens.dashboard_user import UserDashboard
from client.ui.app_config import APP_NAME


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1200x760")
        self.minsize(1100, 700)

        # Track per-portal UI mode to avoid "zombie" frames created by in-screen rebuilds.
        # (Some screens may recreate themselves when toggling light/dark.)
        self.portal_dark_mode = {"admin": True, "employee": True}

        self._frame = None
        self.show_landing()

    def _set_frame(self, frame):
        """Replace the active screen safely.

        If any screen creates extra Frames without going through this method
        (e.g., a theme toggle that rebuilds the screen), those Frames can remain
        visible and overlap the dashboard after login.

        To be resilient, destroy *all* root children except the new frame.
        """
        for child in list(self.winfo_children()):
            if child is frame:
                continue
            try:
                child.destroy()
            except Exception:
                pass
        self._frame = frame

    def show_landing(self):
        self._set_frame(LandingScreen(self, self.choose_portal))

    def choose_portal(self, role: str):
        portal_role = "admin" if role == "admin" else "employee"
        self.show_portal_menu(portal_role)

    def show_portal_menu(self, portal_role: str):
        def back():
            self.show_landing()

        def go_login():
            self.show_login(portal_role)

        def go_register():
            self.show_register(portal_role)

        self._set_frame(PortalMenuScreen(self, portal_role, on_login=go_login, on_register=go_register, on_back=back))

    def show_register(self, portal_role: str):
        def done():
            # After registering, take user back to the portal menu so they can choose to login.
            self.show_portal_menu(portal_role)

        def go_login():
            self.show_login(portal_role)

        self._set_frame(RegisterScreen(self, on_done=done, portal_role=portal_role, on_login=go_login))

    def show_login(self, portal_role: str):
        def on_success(token, role, username):
            try:
                if role == "admin":
                    self._set_frame(AdminDashboard(self, token, role, username))
                else:
                    self._set_frame(UserDashboard(self, token, role, username))
            except Exception as e:
                import tkinter.messagebox as mb
                mb.showerror("Dashboard Error", f"Failed to open dashboard.\n\n{e}")
                # Return to login to avoid leaving the UI in a broken half-state.
                self.show_login(portal_role)

        def back():
            self.show_portal_menu(portal_role)

        def register():
            self.show_register(portal_role)

        self._set_frame(
            LoginScreen(
                self,
                portal_role,
                on_login_success=on_success,
                on_back=back,
                on_register=register,
            )
        )


if __name__ == "__main__":
    App().mainloop()
