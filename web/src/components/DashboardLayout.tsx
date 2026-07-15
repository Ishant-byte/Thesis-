import { Outlet, NavLink, useNavigate } from "react-router-dom";
import {
  Users,
  Calendar,
  Wallet,
  Megaphone,
  MessageSquare,
  FileSignature,
  ScrollText,
  User,
  Clock,
  LogOut,
  Building2,
} from "lucide-react";
import { useEffect, useState } from "react";
import { useAuth } from "../lib/auth";
import { put, wsUrl } from "../lib/api";
import { WSClient, type WSMessage } from "../lib/ws";
import { PRESENCE_STATUSES } from "../lib/constants";

export interface Person {
  username: string;
  role: string;
  department: string;
  presence_state: string;
  last_seen?: string | null;
  job_role?: string;
}

const adminNav = [
  { to: "/dashboard/employees", label: "Employees", icon: Users },
  { to: "/dashboard/leave", label: "Leave", icon: Calendar },
  { to: "/dashboard/salary", label: "Salary", icon: Wallet },
  { to: "/dashboard/notices", label: "Notices", icon: Megaphone },
  { to: "/dashboard/chat", label: "Chat", icon: MessageSquare },
  { to: "/dashboard/documents", label: "Documents", icon: FileSignature },
  { to: "/dashboard/logs", label: "Audit Logs", icon: ScrollText },
  { to: "/dashboard/profile", label: "Profile", icon: User },
];

const employeeNav = [
  { to: "/dashboard/profile", label: "Profile", icon: User },
  { to: "/dashboard/attendance", label: "Attendance", icon: Clock },
  { to: "/dashboard/leave", label: "Leave", icon: Calendar },
  { to: "/dashboard/salary", label: "Salary", icon: Wallet },
  { to: "/dashboard/notices", label: "Notices", icon: Megaphone },
  { to: "/dashboard/chat", label: "Chat", icon: MessageSquare },
  { to: "/dashboard/documents", label: "Documents", icon: FileSignature },
  { to: "/dashboard/logs", label: "My Logs", icon: ScrollText },
];

const WS_CTX = { client: null as WSClient | null, people: [] as Person[], handlers: [] as ((m: WSMessage) => void)[] };

export function getWS() {
  return WS_CTX;
}

export function DashboardLayout() {
  const { session, logout } = useAuth();
  const navigate = useNavigate();
  const [people, setPeople] = useState<Person[]>([]);
  const [status, setStatus] = useState("online");

  useEffect(() => {
    if (!session) {
      navigate("/");
      return;
    }

    const ws = new WSClient(wsUrl(session.token));
    WS_CTX.client = ws;

    const unsub = ws.onMessage((msg) => {
      if (msg.type === "presence_list") {
        const p = (msg.people as Person[]) ?? [];
        setPeople(p);
        WS_CTX.people = p;
      }
      WS_CTX.handlers.forEach((h) => h(msg));
    });

    ws.start();

    return () => {
      unsub();
      ws.stop();
      WS_CTX.client = null;
    };
  }, [session, navigate]);

  const handleStatus = async (s: string) => {
    setStatus(s);
    WS_CTX.client?.send({ type: "set_status", status: s });
    if (session) {
      try {
        await put("/me/status", { presence_state: s }, session.token);
      } catch {
        /* ignore */
      }
    }
  };

  const handleLogout = async () => {
    if (session) {
      try {
        await put("/me/status", { presence_state: "offline" }, session.token);
      } catch {
        /* ignore */
      }
    }
    WS_CTX.client?.stop();
    logout();
    navigate("/");
  };

  if (!session) return null;

  const nav = session.role === "admin" ? adminNav : employeeNav;
  const presenceColor: Record<string, string> = {
    online: "bg-emerald-500",
    away: "bg-amber-400",
    home: "bg-blue-400",
    offline: "bg-slate-300",
  };

  return (
    <div className="flex min-h-screen bg-slate-50">
      {/* Sidebar */}
      <aside className="flex w-64 flex-col border-r border-slate-200 bg-white">
        <div className="flex items-center gap-2 border-b border-slate-200 px-5 py-4">
          <Building2 className="h-6 w-6 text-brand-700" />
          <div>
            <div className="text-sm font-semibold text-slate-900">PramaanHR</div>
            <div className="text-xs text-slate-500 capitalize">{session.role} Portal</div>
          </div>
        </div>

        <nav className="flex-1 space-y-0.5 p-3">
          {nav.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition ${
                  isActive
                    ? "bg-brand-50 text-brand-800"
                    : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
                }`
              }
            >
              <Icon className="h-4 w-4 shrink-0" />
              {label}
            </NavLink>
          ))}
        </nav>

        {/* Presence panel */}
        <div className="border-t border-slate-200 p-4">
          <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Team Presence</div>
          <select
            className="input-field mb-3 text-xs"
            value={status}
            onChange={(e) => handleStatus(e.target.value)}
          >
            {PRESENCE_STATUSES.map((s) => (
              <option key={s} value={s}>
                My status: {s}
              </option>
            ))}
          </select>
          <div className="max-h-40 space-y-1 overflow-y-auto">
            {people
              .filter((p) => p.username !== session.username)
              .map((p) => (
                <div key={p.username} className="flex items-center gap-2 text-xs text-slate-600">
                  <span className={`h-2 w-2 shrink-0 rounded-full ${presenceColor[p.presence_state] ?? "bg-slate-300"}`} />
                  <span className="truncate">{p.username.split("@")[0]}</span>
                  {p.department && <span className="text-slate-400">· {p.department}</span>}
                </div>
              ))}
          </div>
        </div>

        <div className="border-t border-slate-200 p-4">
          <div className="mb-2 truncate text-xs text-slate-500">{session.username}</div>
          <button
            onClick={handleLogout}
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-slate-600 hover:bg-slate-50"
          >
            <LogOut className="h-4 w-4" />
            Sign out
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto p-8">
        <Outlet context={{ people, session }} />
      </main>
    </div>
  );
}
