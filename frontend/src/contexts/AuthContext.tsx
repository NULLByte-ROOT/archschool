import { createContext, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import {
  fetchMe,
  login as apiLogin,
  register as apiRegister,
} from "../api/client";
import type { User } from "../api/client";

interface AuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  /** admin or owner — manages assignments, users and chat. */
  isAdmin: boolean;
  /** owner — server stats, code changes, role grants above admin. */
  isOwner: boolean;
  /** friend — chats + comments, but never manages assignments. */
  isFriend: boolean;
  /** plain member — read-only everywhere except their own completion toggles. */
  isMember: boolean;
  login: (username: string, code: string) => Promise<void>;
  register: (username: string, code: string) => Promise<void>;
  refreshUser: () => Promise<void>;
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

  const persist = (data: { access_token: string; user: User }) => {
    localStorage.setItem("token", data.access_token);
    localStorage.setItem("user", JSON.stringify(data.user));
    setUser(data.user);
  };

  const login = async (username: string, code: string) => {
    persist(await apiLogin(username, code));
  };

  const register = async (username: string, code: string) => {
    persist(await apiRegister(username, code));
  };

  const refreshUser = async () => {
    const fresh = await fetchMe();
    localStorage.setItem("user", JSON.stringify(fresh));
    setUser(fresh);
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
        isAdmin:
          !!user?.is_admin || user?.role === "admin" || user?.role === "owner",
        isOwner: user?.role === "owner",
        isFriend: user?.role === "friend",
        isMember: !!user && user.role === "member" && !user.is_admin,
        login,
        register,
        refreshUser,
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