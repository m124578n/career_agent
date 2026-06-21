import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { setAuthToken, setOnUnauthorized } from "../api/client";

const CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID;
const KEY = "jobtracker.token";

export interface AuthUser {
  email: string;
  name?: string;
  picture?: string;
}

interface AuthCtx {
  enabled: boolean; // 是否啟用 Google 登入（未設 client id → false）
  token: string | null;
  user: AuthUser | null;
  login: (credential: string) => void;
  logout: () => void;
}

const Ctx = createContext<AuthCtx | null>(null);

function decode(token: string): AuthUser | null {
  try {
    const base64 = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    const json = decodeURIComponent(
      atob(base64)
        .split("")
        .map((c) => "%" + c.charCodeAt(0).toString(16).padStart(2, "0"))
        .join(""),
    );
    const p = JSON.parse(json);
    return { email: p.email, name: p.name, picture: p.picture };
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const enabled = !!CLIENT_ID;
  const [token, setToken] = useState<string | null>(() =>
    enabled ? localStorage.getItem(KEY) : null,
  );

  useEffect(() => {
    setAuthToken(token);
    if (token) localStorage.setItem(KEY, token);
    else localStorage.removeItem(KEY);
  }, [token]);

  useEffect(() => {
    setOnUnauthorized(() => setToken(null));
    return () => setOnUnauthorized(null);
  }, []);

  const user = token ? decode(token) : null;

  return (
    <Ctx.Provider
      value={{ enabled, token, user, login: setToken, logout: () => setToken(null) }}
    >
      {children}
    </Ctx.Provider>
  );
}

export function useAuth() {
  const c = useContext(Ctx);
  if (!c) throw new Error("useAuth 必須在 AuthProvider 內使用");
  return c;
}
