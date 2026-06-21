import type { ReactNode } from "react";
import { useAuth } from "../state/auth";
import { LoginScreen } from "./LoginScreen";

/** 啟用登入且未登入 → 顯示登入畫面；否則放行。 */
export function AuthGate({ children }: { children: ReactNode }) {
  const { enabled, token } = useAuth();
  if (enabled && !token) return <LoginScreen />;
  return <>{children}</>;
}
