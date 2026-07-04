import { useEffect, useState } from "react";

/** active 為真時每秒 +1，轉 false 歸零。 */
export function useElapsed(active: boolean): number {
  const [n, setN] = useState(0);
  useEffect(() => {
    if (!active) {
      setN(0);
      return;
    }
    setN(0);
    const id = setInterval(() => setN((x) => x + 1), 1000);
    return () => clearInterval(id);
  }, [active]);
  return n;
}
