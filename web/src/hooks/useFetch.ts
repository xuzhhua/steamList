import { useCallback, useEffect, useRef, useState } from 'react';

interface UseFetchOptions {
  /** 轮询间隔（毫秒），为 0 / 未设置时不轮询。 */
  pollMs?: number;
  /** 为 false 时暂停加载（依赖变化后自动重跑）。 */
  enabled?: boolean;
}

interface UseFetchResult<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => Promise<void>;
  setData: (data: T | null) => void;
}

/**
 * 极简数据请求 hook：加载状态 / 错误 / 手动重载 / 可选轮询。
 * loader 需由调用方用 useCallback 固定，避免无限请求。
 */
export function useFetch<T>(loader: () => Promise<T>, deps: unknown[], options: UseFetchOptions = {}): UseFetchResult<T> {
  const { pollMs = 0, enabled = true } = options;
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(enabled);
  const [tick, setTick] = useState(0);
  const mountedRef = useRef(true);
  const loaderRef = useRef(loader);

  loaderRef.current = loader;

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    let inFlight = false;

    const run = async (showLoading: boolean) => {
      if (inFlight) return;
      inFlight = true;
      if (showLoading) setLoading(true);
      try {
        const result = await loaderRef.current();
        if (cancelled || !mountedRef.current) return;
        setData(result);
        setError(null);
      } catch (err) {
        if (cancelled || !mountedRef.current) return;
        setError(err instanceof Error ? err.message : '加载失败');
      } finally {
        inFlight = false;
        if (!cancelled && mountedRef.current) setLoading(false);
      }
    };

    void run(true);

    let timer: number | undefined;
    if (pollMs > 0) {
      timer = window.setInterval(() => {
        void run(false);
      }, pollMs);
    }

    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearInterval(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, pollMs, tick, ...deps]);

  const reload = useCallback(async () => {
    setTick((value) => value + 1);
  }, []);

  return { data, error, loading, reload, setData };
}
