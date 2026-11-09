import { useCallback, useEffect, useState, type DependencyList } from "react";

/** Run an async loader and track its result; re-runs when deps change. */
export function useAsync<T>(fn: () => Promise<T>, deps: DependencyList) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const depsKey = JSON.stringify(deps);
  const [lastKey, setLastKey] = useState(depsKey);
  if (lastKey !== depsKey) {
    // New inputs: drop the previous result so stale data is never shown.
    setLastKey(depsKey);
    setData(null);
  }

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    fn()
      .then((d) => alive && setData(d))
      .catch((e: Error) => alive && setError(e.message))
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data, error, loading, reload, setData };
}
