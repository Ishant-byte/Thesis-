import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

export interface AuthSession {
  token: string;
  role: "admin" | "employee";
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

  const value = useMemo(() => ({ session, setSession, logout }), [session]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
