from __future__ import annotations
import tkinter as tk

from client.ui.screens.dashboard_base import DashboardBase
from client.ui.themes.themes import ADMIN_THEME
from client.ui.screens.profile_tab import ProfileTab
from client.ui.screens.employees_tab import EmployeesTab
from client.ui.screens.notices_tab import NoticesTab
from client.ui.screens.logs_tab import LogsTab
from client.ui.screens.chat_tab import ChatTab
from client.ui.screens.documents_tab import DocumentsTab
from client.ui.screens.leave_tab import LeaveTab
from client.ui.screens.salary_tab import SalaryTab

class AdminDashboard(DashboardBase):
    def __init__(self, master, token: str, role: str, username: str):
        super().__init__(master, token, role, username, ADMIN_THEME)

        self.add_tab("Employees", EmployeesTab(self.nb, self))
        self.add_tab("Leave", LeaveTab(self.nb, self))
        self.add_tab("Salary", SalaryTab(self.nb, self))
        self.add_tab("Notices", NoticesTab(self.nb, self))
        self.add_tab("Chat", ChatTab(self.nb, self))
        self.add_tab("Documents", DocumentsTab(self.nb, self))
        self.add_tab("Logs", LogsTab(self.nb, self))
        self.add_tab("Profile", ProfileTab(self.nb, self))
