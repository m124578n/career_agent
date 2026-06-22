import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import type { ResumeDiagnosis, ResumeTarget } from "../types";

interface ResumeCtx {
  target: ResumeTarget | null;
  setTarget: (t: ResumeTarget | null) => void;
  diagnosis: ResumeDiagnosis | null;
  setDiagnosis: (d: ResumeDiagnosis | null) => void;
}

const Ctx = createContext<ResumeCtx | null>(null);
const KEY = "jobtracker.resume-target";
const DIAG_KEY = "jobtracker.resume-diagnosis";

function load<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

export function ResumeProvider({ children }: { children: ReactNode }) {
  const [target, setTarget] = useState<ResumeTarget | null>(() =>
    load<ResumeTarget>(KEY)
  );
  const [diagnosis, setDiagnosis] = useState<ResumeDiagnosis | null>(() =>
    load<ResumeDiagnosis>(DIAG_KEY)
  );

  useEffect(() => {
    if (target) localStorage.setItem(KEY, JSON.stringify(target));
    else localStorage.removeItem(KEY);
  }, [target]);

  useEffect(() => {
    if (diagnosis) localStorage.setItem(DIAG_KEY, JSON.stringify(diagnosis));
    else localStorage.removeItem(DIAG_KEY);
  }, [diagnosis]);

  return (
    <Ctx.Provider value={{ target, setTarget, diagnosis, setDiagnosis }}>
      {children}
    </Ctx.Provider>
  );
}

export function useResume() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useResume 必須在 ResumeProvider 內使用");
  return ctx;
}
