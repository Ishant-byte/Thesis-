import { createContext, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { AUTH_LOGOUT_EVENT, type AuthLogoutEventDetail } from "./api";

export interface AuthSession {
  token: string;
  role: "super_admin" | "admin" | "employee";
  username: string;
  keystore?: ArrayBuffer;
  keystorePassword?: string;
}

interface AuthContextValue {
  session: AuthSession | null;
  setSession: (s: AuthSession | null) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const STORAGE_KEY = "pramaanhr_session";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [forcedLogoutReason, setForcedLogoutReason] = useState("");
  const logoutTimer = useRef<number>();
  const [session, setSessionState] = useState<AuthSession | null>(() => {
    try {
      const raw = sessionStorage.getItem(STORAGE_KEY);
      if (!raw) return null;
      const parsed = JSON.parse(raw) as Omit<AuthSession, "keystore">;
      return { ...parsed, keystore: undefined, keystorePassword: undefined };
    } catch {
      return null;
    }
  });

  const setSession = (s: AuthSession | null) => {
    setSessionState(s);
    if (s) {
      sessionStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ token: s.token, role: s.role, username: s.username })
      );
    } else {
      sessionStorage.removeItem(STORAGE_KEY);
    }
  };

  const logout = () => setSession(null);

  useEffect(() => {
    const handleForcedLogout = (rawEvent: Event) => {
      if (logoutTimer.current !== undefined) return;
      const { reason, redirectPath } = (rawEvent as CustomEvent<AuthLogoutEventDetail>).detail;
      setForcedLogoutReason(reason);
      logoutTimer.current = window.setTimeout(() => window.location.assign(redirectPath), 4000);
    };
    window.addEventListener(AUTH_LOGOUT_EVENT, handleForcedLogout);
    return () => {
      window.removeEventListener(AUTH_LOGOUT_EVENT, handleForcedLogout);
      if (logoutTimer.current !== undefined) window.clearTimeout(logoutTimer.current);
    };
  }, []);

  const value = useMemo(() => ({ session, setSession, logout }), [session]);

  return (
    <AuthContext.Provider value={value}>
      {children}
      {forcedLogoutReason && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/50 px-4">
          <div
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="forced-logout-title"
            className="w-full max-w-md rounded-xl bg-white p-6 text-center shadow-2xl"
          >
            <h2 id="forced-logout-title" className="text-xl font-semibold text-slate-900">
              You have been signed out
            </h2>
            <p className="mt-3 text-slate-700">{forcedLogoutReason}</p>
            <p className="mt-4 text-sm text-slate-500">Redirecting to sign in in 4 seconds…</p>
          </div>
        </div>
      )}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
