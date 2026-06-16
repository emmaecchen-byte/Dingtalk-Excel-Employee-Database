import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { AuthUser } from "./storage";
import * as authApi from "./api";
import { hasStoredSession } from "./storage";

interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  loginWithTokens: (accessToken: string, refreshToken: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshUser = useCallback(async () => {
    const currentUser = await authApi.fetchCurrentUser();
    setUser(currentUser);
  }, []);

  useEffect(() => {
    const bootstrap = async () => {
      if (!hasStoredSession()) {
        setLoading(false);
        return;
      }
      try {
        await refreshUser();
      } catch {
        await authApi.logout();
        setUser(null);
      } finally {
        setLoading(false);
      }
    };
    bootstrap();
  }, [refreshUser]);

  const login = useCallback(async (email: string, password: string) => {
    const result = await authApi.login(email, password);
    setUser(result.user);
  }, []);

  const loginWithTokens = useCallback(async (accessToken: string, refreshToken: string) => {
    const currentUser = await authApi.completeDingTalkLogin(accessToken, refreshToken);
    setUser(currentUser);
  }, []);

  const logout = useCallback(async () => {
    await authApi.logout();
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({
      user,
      loading,
      isAuthenticated: Boolean(user),
      login,
      loginWithTokens,
      logout,
      refreshUser,
    }),
    [user, loading, login, loginWithTokens, logout, refreshUser]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
}
