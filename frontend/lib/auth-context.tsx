"use client";

import { createContext, useContext, useMemo, useState } from "react";
import type { AuthSession } from "@/lib/data";
import { clearStoredAuthSession, writeStoredAuthSession } from "@/lib/auth-store";

type AuthContextValue = {
  session: AuthSession | null;
  isAuthenticated: boolean;
  isModerator: boolean;
  setSession: (session: AuthSession | null) => Promise<void>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSessionState] = useState<AuthSession | null>(null);

  const value = useMemo<AuthContextValue>(() => ({
    session,
    isAuthenticated: Boolean(session?.token),
    isModerator: session?.role === "moderator",
    setSession: async (nextSession) => {
      setSessionState(nextSession);
      if (nextSession) {
        await writeStoredAuthSession(nextSession);
      } else {
        await clearStoredAuthSession();
      }
    },
    logout: async () => {
      setSessionState(null);
      await clearStoredAuthSession();
    },
  }), [session]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error("useAuth deve ser usado dentro de AuthProvider.");
  }
  return value;
}
