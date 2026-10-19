import { useEffect, useState } from "react";

/** Returns the current timestamp, refreshed on an interval so time-based UI stays live. */
export function useNow(interval = 30_000): number {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), interval);
    return () => clearInterval(id);
  }, [interval]);

  return now;
}
