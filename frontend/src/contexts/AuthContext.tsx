import { createContext, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { fetchMe, login as apiLogin } from "../api/client";
import type { User } from "../api/client";

interface AuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  isAdmin: boolean;
  isEditor: boolean;
  login: (username: string, code: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(() => {
    const raw = localStorage.getItem("user");
    if (!raw) return null;
    try {
      return { points: 0, ...JSON.parse(raw) } as User;
    } catch {
      return null;
    }
  });

  // Refresh the cached user on load so role changes made in the admin panel
  // take effect without forcing a re-login.
  useEffect(() => {
    if (!localStorage.getItem("token")) return;
    let active = true;
    fetchMe()
      .then((fresh) => {
        if (!active) return;
        localStorage.setItem("user", JSON.stringify(fresh));
        setUser(fresh);
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);

  const login = async (username: string, code: string) => {
    const data = await apiLogin(username, code);
    localStorage.setItem("token", data.access_token);
    localStorage.setItem("user", JSON.stringify(data.user));
    setUser(data.user);
  };

  const logout = () => {
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    setUser(null);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: !!user,
        isAdmin: !!user?.is_admin || user?.role === "admin",
        isEditor: user?.role === "editor",
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be inside AuthProvider");
  return ctx;
}