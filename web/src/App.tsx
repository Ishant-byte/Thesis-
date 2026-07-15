import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./lib/auth";
import { DashboardLayout } from "./components/DashboardLayout";
import { LandingPage } from "./pages/Landing";
import { PortalMenuPage } from "./pages/PortalMenu";
import { LoginPage } from "./pages/Login";
import { RegisterPage } from "./pages/Register";
import { ProfilePage } from "./pages/Profile";
import { AttendancePage } from "./pages/Attendance";
import { LeavePage } from "./pages/Leave";
import { SalaryPage } from "./pages/Salary";
import { NoticesPage } from "./pages/Notices";
import { ChatPage } from "./pages/Chat";
import { DocumentsPage } from "./pages/Documents";
import { LogsPage } from "./pages/Logs";
import { EmployeesPage } from "./pages/Employees";
import type { ReactNode } from "react";

function Protected({ children }: { children: ReactNode }) {
  const { session } = useAuth();
  if (!session) return <Navigate to="/" replace />;
  return <>{children}</>;
}

function AdminOnly({ children }: { children: ReactNode }) {
  const { session } = useAuth();
  if (!session || session.role !== "admin") return <Navigate to="/dashboard/profile" replace />;
  return <>{children}</>;
}

function EmployeeOnly({ children }: { children: ReactNode }) {
  const { session } = useAuth();
  if (!session || session.role !== "employee") return <Navigate to="/dashboard/profile" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/portal/:role" element={<PortalMenuPage />} />
          <Route path="/login/:role" element={<LoginPage />} />
          <Route path="/register/:role" element={<RegisterPage />} />

          <Route
            path="/dashboard"
            element={
              <Protected>
                <DashboardLayout />
              </Protected>
            }
          >
            <Route index element={<Navigate to="profile" replace />} />
            <Route path="profile" element={<ProfilePage />} />
            <Route
              path="attendance"
              element={
                <EmployeeOnly>
                  <AttendancePage />
                </EmployeeOnly>
              }
            />
            <Route path="leave" element={<LeavePage />} />
            <Route path="salary" element={<SalaryPage />} />
            <Route path="notices" element={<NoticesPage />} />
            <Route path="chat" element={<ChatPage />} />
            <Route path="documents" element={<DocumentsPage />} />
            <Route path="logs" element={<LogsPage />} />
            <Route
              path="employees"
              element={
                <AdminOnly>
                  <EmployeesPage />
                </AdminOnly>
              }
            />
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
