from __future__ import annotations
import tkinter as tk
from client import api
from client.ui.widgets.base import make_label, make_button

class AttendanceTab(tk.Frame):
    def __init__(self, master, dashboard):
        super().__init__(master, bg=dashboard.theme["panel"])
        self.d = dashboard
        self.theme = dashboard.theme

        make_label(self, "Attendance", self.theme, size=14, bold=True).pack(anchor="w", padx=12, pady=(12,6))
        btns = tk.Frame(self, bg=self.theme["panel"])
        btns.pack(anchor="w", padx=12, pady=(0,8))
        make_button(btns, "Clock In", self.theme, lambda: self.act("clock_in")).pack(side="left")
        make_button(btns, "Clock Out", self.theme, lambda: self.act("clock_out")).pack(side="left", padx=10)
        make_button(btns, "Refresh", self.theme, self.refresh).pack(side="left", padx=10)

        self.info = make_label(self, "", self.theme, size=10)
        self.info.pack(anchor="w", padx=12)

        wrap = tk.Frame(self, bg=self.theme["panel"])
        wrap.pack(fill="both", expand=True, padx=12, pady=12)
        self.list = tk.Listbox(wrap, bg=self.theme["bg0"], fg=self.theme["text"], highlightthickness=1, highlightbackground=self.theme["accent"])
        sb = tk.Scrollbar(wrap, orient="vertical", command=self.list.yview)
        self.list.configure(yscrollcommand=sb.set)
        self.list.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.refresh()

    def act(self, action: str):
        try:
            api.post("/me/attendance", {"action": action}, token=self.d.token)
            self.info.config(text=f"{action.replace('_',' ').title()} recorded.")
            self.refresh()
        except api.APIError as e:
            self.info.config(text=str(e))

    def refresh(self):
        self.list.delete(0,"end")
        try:
            data = api.get("/me/attendance", token=self.d.token)
            for r in data.get("records", []):
                self.list.insert("end", f"{r['date']}  IN={r.get('clock_in')}  OUT={r.get('clock_out')}")
        except api.APIError as e:
            self.info.config(text=str(e))
