import { useCallback, useState } from 'react';
import { api } from '../lib/api';
import type { JobStatus } from '../lib/types';
import { useFetch } from './useFetch';

/** 全局任务状态轮询 + 手动触发数据刷新。 */
export function useJobStatus(pollMs = 5000) {
  const load = useCallback(() => api.getJobStatus(), []);
  const { data, loading, reload, setData } = useFetch<JobStatus>(load, [], { pollMs });
  const [starting, setStarting] = useState(false);

  const startRefresh = useCallback(async (): Promise<boolean> => {
    if (starting) return false;
    setStarting(true);
    try {
      await api.refreshJobs();
      await reload();
      return true;
    } finally {
      setStarting(false);
    }
  }, [reload, starting]);

  return { status: data, loading, reload, setData, startRefresh, starting };
}
