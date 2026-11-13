import { useCallback, useEffect, useRef, useState, type DependencyList } from "react";

import { errorMessage } from "../api/client";

export function useApi<T>(loader: () => Promise<T>, deps: DependencyList) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const latestRequest = useRef(0);

  const reload = useCallback(async () => {
    const requestId = ++latestRequest.current;
    setLoading(true);
    setError(null);

    try {
      const result = await loader();
      if (requestId === latestRequest.current) setData(result);
    } catch (caught) {
      if (requestId === latestRequest.current) setError(errorMessage(caught));
    } finally {
      if (requestId === latestRequest.current) setLoading(false);
    }
    // The caller's dependency list controls when the loader changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { data, loading, error, reload, setData };
}