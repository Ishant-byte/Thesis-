from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable, Optional

from client import api
from client.ws_client import WSClient
from client.ui.widgets.base import AnimatedBackground, make_label
from client.ui.app_config import APP_NAME, LOGO_PATH
from client.ui.themes.themes import ADMIN_THEME, USER_THEME

class DashboardBase(tk.Frame):
    def __init__(self, master, token: str, role: str, username: str, theme: dict):
        super().__init__(master)
        self.token = token
        self.role = role
        self.username = username
        self.theme = theme
        self.dark_mode = True

        self.pack(fill="both", expand=True)

        self.bg = AnimatedBackground(self, self.theme)
        self.bg.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.bg.start()

        self.container = tk.Frame(self, bg=self.theme["panel"])
        self.container.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.92, relheight=0.9)

        # Topbar
        self.top = tk.Frame(self.container, bg=self.theme["panel"])
        self.top.pack(fill="x", padx=10, pady=8)

        self._logo_img = None
        try:
            # Do NOT re-import tkinter inside this method.
            # Re-importing would shadow the module-level `tk` name and can
            # trigger UnboundLocalError ("cannot access local variable 'tk'").
            self._logo_img = tk.PhotoImage(file=str(LOGO_PATH)).subsample(4, 4)
            tk.Label(self.top, image=self._logo_img, bg=self.theme["panel"]).pack(side="left", padx=(0, 10))
        except Exception:
            pass

        make_label(self.top, APP_NAME, self.theme, size=13, bold=True).pack(side="left")
        make_label(self.top, f" • {'Admin' if role=='admin' else 'Employee'}", self.theme, size=11).pack(side="left", padx=(6, 14))
        make_label(self.top, f" {username}", self.theme, size=10).pack(side="left", padx=10)

        self.mode_btn = tk.Button(self.top, text="☾ / ☀", command=self.toggle_mode, bg=self.theme["panel"], fg=self.theme["muted"], relief="flat")
        self.mode_btn.pack(side="right", padx=8)

        # Logout (always available; closes WS + returns to landing)
        self.logout_btn = tk.Button(
            self.top,
            text="Logout",
            command=self.logout,
            bg=self.theme["bg0"],
            fg=self.theme["text"],
            relief="flat",
            padx=12,
            pady=2,
        )
        self.logout_btn.pack(side="right", padx=6)

        # Body split: sidebar + main
        self.body = tk.Frame(self.container, bg=self.theme["panel"])
        self.body.pack(fill="both", expand=True, padx=10, pady=(0,10))

        self.sidebar = tk.Frame(self.body, bg=self.theme["panel"])
        self.sidebar.pack(side="left", fill="y", padx=(0,10))
        self.main = tk.Frame(self.body, bg=self.theme["panel"])
        self.main.pack(side="right", fill="both", expand=True)

        make_label(self.sidebar, "Presence", self.theme, size=11, bold=True).pack(anchor="w", pady=(0,6))
        pres_wrap = tk.Frame(self.sidebar, bg=self.theme["panel"])
        pres_wrap.pack(fill="y", expand=True)
        self.presence_list = tk.Listbox(pres_wrap, width=34, bg=self.theme["bg0"], fg=self.theme["text"], highlightthickness=1, highlightbackground=self.theme["accent"], selectbackground=self.theme["accent"])
        pres_sb = tk.Scrollbar(pres_wrap, orient="vertical", command=self.presence_list.yview)
        self.presence_list.configure(yscrollcommand=pres_sb.set)
        self.presence_list.pack(side="left", fill="y", expand=True)
        pres_sb.pack(side="right", fill="y")

        self.status_var = tk.StringVar(value="online")
        status_row = tk.Frame(self.sidebar, bg=self.theme["panel"])
        status_row.pack(fill="x", pady=(8,0))
        make_label(status_row, "My status:", self.theme, size=10).pack(side="left")
        opts = ["online","away","home","offline"]
        self.status_menu = tk.OptionMenu(status_row, self.status_var, *opts, command=lambda _: self.set_status())
        self.status_menu.configure(bg=self.theme["bg0"], fg=self.theme["text"], relief="flat", highlightthickness=0)
        self.status_menu.pack(side="right")

        # Notebook
        style = ttk.Style()
        style.theme_use("default")
        style.configure("TNotebook", background=self.theme["panel"], borderwidth=0)
        style.configure("TNotebook.Tab", background=self.theme["bg0"], foreground=self.theme["text"], padding=(12,8))
        style.map("TNotebook.Tab", background=[("selected", self.theme["accent"])])
        self.nb = ttk.Notebook(self.main)
        self.nb.pack(fill="both", expand=True)

        # WebSocket
        self.ws = None
        self.chat_callbacks = []
        self._connect_ws()

    def toggle_mode(self):
        self.dark_mode = not self.dark_mode
        # Toggle only panel/bg contrast; keep accent
        if self.dark_mode:
            # reset to original theme palette by role
            from client.ui.themes.themes import ADMIN_THEME, USER_THEME
            self.theme = ADMIN_THEME if self.role=="admin" else USER_THEME
        else:
            t = dict(self.theme)
            t["bg0"], t["bg1"] = t["bg1"], t["bg0"]
            t["panel"] = t["bg1"]
            self.theme = t
        # Apply to main containers
        self.container.configure(bg=self.theme["panel"])
        self.top.configure(bg=self.theme["panel"])
        self.body.configure(bg=self.theme["panel"])
        self.sidebar.configure(bg=self.theme["panel"])
        self.main.configure(bg=self.theme["panel"])
        self.bg.theme = self.theme

        # Apply to buttons
        try:
            self.mode_btn.configure(bg=self.theme["panel"], fg=self.theme["muted"])
            self.logout_btn.configure(bg=self.theme["bg0"], fg=self.theme["text"])
        except Exception:
            pass

    def logout(self):
        if not messagebox.askyesno("Logout", "Sign out and return to the portal selection?"):
            return

        # Best-effort presence update (WS disconnect also sets offline).
        try:
            api.put("/me/status", {"presence_state": "offline"}, token=self.token)
        except Exception:
            pass

        # Close WS to prevent orphan presence/chat sessions.
        try:
            if self.ws:
                self.ws.stop()
        except Exception:
            pass

        # Navigate back to landing using the root App controller.
        try:
            if hasattr(self.master, "show_landing"):
                self.master.show_landing()
            else:
                self.destroy()
        except Exception:
            try:
                self.destroy()
            except Exception:
                pass

    def _connect_ws(self):
        # verify server
        try:
            api.health()
        except Exception:
            messagebox.showerror("Server/DB", "Server not reachable. Start MongoDB + server.")
            return
        import os
        host = os.getenv("SERVER_HOST", "127.0.0.1")
        port = int(os.getenv("SERVER_PORT", "8765"))
        ws_url = f"ws://{host}:{port}/ws?token={self.token}"

        def on_msg(m):
            if m.get("type") == "presence_list":
                self._update_presence(m.get("people", []))
            for cb in self.chat_callbacks:
                cb(m)

        self.ws = WSClient(ws_url, on_message=on_msg)
        self.ws.start()
        # request initial presence via ping
        self.ws.send({"type":"ping"})

    def _update_presence(self, people):
        self.presence_list.delete(0, tk.END)
        # store for lookups
        self._people = people
        for p in people:
            state = p.get("presence_state","offline")
            role = p.get("role","employee")
            dept = (p.get("department") or "").strip()
            uname = (p.get("username") or "").strip()
            # Show username + department for clarity (requested)
            if dept:
                line = f"[{state:<7}] ({role}) {uname} • {dept}"
            else:
                line = f"[{state:<7}] ({role}) {uname}"
            self.presence_list.insert(tk.END, line)

    def set_status(self):
        if self.ws:
            self.ws.send({"type":"set_status","status": self.status_var.get()})
        try:
            api.put("/me/status", {"presence_state": self.status_var.get()}, token=self.token)
        except Exception:
            pass

    def add_tab(self, title: str, frame: tk.Frame):
        self.nb.add(frame, text=title)

    def on_ws(self, callback: Callable[[dict], None]):
        self.chat_callbacks.append(callback)

    def destroy(self):
        # Ensure websocket is closed when leaving dashboard (prevents orphan sessions).
        try:
            if self.ws:
                self.ws.stop()
        except Exception:
            pass
        super().destroy()
