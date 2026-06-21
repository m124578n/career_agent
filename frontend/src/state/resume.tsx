import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import type { ResumeTarget } from "../types";

interface ResumeCtx {
  target: ResumeTarget | null;
  setTarget: (t: ResumeTarget | null) => void;
}

const Ctx = createContext<ResumeCtx | null>(null);
const KEY = "jobtracker.resume-target";

export function ResumeProvider({ children }: { children: ReactNode }) {
  const [target, setTarget] = useState<ResumeTarget | null>(() => {
    try {
      const raw = localStorage.getItem(KEY);
      return raw ? (JSON.parse(raw) as ResumeTarget) : null;
    } catch {
      return null;
    }
  });

  useEffect(() => {
    if (target) localStorage.setItem(KEY, JSON.stringify(target));
    else localStorage.removeItem(KEY);
  }, [target]);

  return <Ctx.Provider value={{ target, setTarget }}>{children}</Ctx.Provider>;
}

export function useResume() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useResume 必須在 ResumeProvider 內使用");
  return ctx;
}
