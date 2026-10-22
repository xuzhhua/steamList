import type {
  BackupItem,
  BackupList,
  Channel,
  GameDetailResponse,
  ImportResult,
  JobStatus,
  NotificationLogItem,
  NotificationTestResult,
  RangeKey,
  SearchItem,
  SeriesResponse,
  Settings,
  StatsResponse,
  WatchItem,
  WatchlistResponse,
} from './types';

const API_BASE = '/api';

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

function extractDetail(payload: unknown): string | null {
  if (!payload || typeof payload !== 'object') return null;
  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => {
        if (item && typeof item === 'object') {
          const msg = (item as { msg?: unknown }).msg;
          const loc = (item as { loc?: unknown }).loc;
          const where = Array.isArray(loc) ? loc.filter((x) => x !== 'body').join('.') : '';
          if (typeof msg === 'string') return where ? `${where}: ${msg}` : msg;
        }
        return null;
      })
      .filter((x): x is string => !!x);
    if (parts.length > 0) return parts.join('；');
  }
  return null;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      headers: init?.body !== undefined ? { 'Content-Type': 'application/json', ...(init?.headers ?? {}) } : init?.headers,
      ...init,
    });
  } catch (err) {
    throw new ApiError(err instanceof Error ? `网络请求失败：${err.message}` : '网络请求失败', 0);
  }

  if (!response.ok) {
    let message = `请求失败（HTTP ${response.status}）`;
    try {
      const payload: unknown = await response.json();
      message = extractDetail(payload) ?? message;
    } catch {
      /* 非 JSON 响应 */
    }
    throw new ApiError(message, response.status);
  }

  if (response.status === 204) return undefined as T;
  try {
    return (await response.json()) as T;
  } catch {
    return undefined as T;
  }
}

export const api = {
  // 关注列表
  getWatchlist: () => request<WatchlistResponse>('/watchlist'),

  addWatch: (body: {
    appid: number;
    target_price_cents?: number | null;
    discount_alert_threshold?: number | null;
    note?: string;
    notify_enabled?: boolean;
  }) => request<WatchItem>('/watchlist', { method: 'POST', body: JSON.stringify(body) }),

  patchWatch: (
    appid: number,
    body: Partial<{
      target_price_cents: number | null;
      discount_alert_threshold: number | null;
      note: string;
      notify_enabled: boolean;
      sort_order: number;
    }>,
  ) => request<WatchItem>(`/watchlist/${appid}`, { method: 'PATCH', body: JSON.stringify(body) }),

  deleteWatch: (appid: number) => request<void>(`/watchlist/${appid}`, { method: 'DELETE' }),

  importWishlist: (body: { steamid?: string; limit?: number }) =>
    request<ImportResult>('/watchlist/import', { method: 'POST', body: JSON.stringify(body) }),

  // 游戏
  searchGames: (term: string) =>
    request<{ items: SearchItem[] }>(`/games/search?term=${encodeURIComponent(term)}`),

  getGame: (appid: number) => request<GameDetailResponse>(`/games/${appid}`),

  getSeries: (appid: number, range: RangeKey) =>
    request<SeriesResponse>(`/games/${appid}/series?range=${range}`),

  getStats: (appid: number) => request<StatsResponse>(`/games/${appid}/stats`),

  // 设置
  getSettings: () => request<Settings>('/settings'),

  putSettings: (body: Partial<Settings>) =>
    request<Settings>('/settings', { method: 'PUT', body: JSON.stringify(body) }),

  // 任务
  refreshJobs: () => request<{ job_id: number; status: string }>('/jobs/refresh', { method: 'POST' }),

  getJobStatus: () => request<JobStatus>('/jobs/status'),

  // 通知
  testNotification: (channelId?: number) =>
    request<{ results: NotificationTestResult[] }>('/notifications/test', {
      method: 'POST',
      body: JSON.stringify(channelId === undefined ? {} : { channel_id: channelId }),
    }),

  getNotificationLog: (limit = 50) =>
    request<{ items: NotificationLogItem[] }>(`/notifications/log?limit=${limit}`),

  // 备份
  listBackups: () => request<BackupList>('/backup'),

  createBackup: () => request<BackupItem>('/backup', { method: 'POST' }),
};

export function backupDownloadUrl(name: string): string {
  return `${API_BASE}/backup/download?name=${encodeURIComponent(name)}`;
}

export function channelConfigSummary(channel: Channel): string {
  const config = channel.config ?? {};
  switch (channel.kind) {
    case 'bark':
      return typeof config.url === 'string' ? config.url : '未配置 Bark 地址';
    case 'webhook':
      return typeof config.url === 'string' ? config.url : '未配置 Webhook 地址';
    case 'email':
      return typeof config.to_addrs === 'string'
        ? config.to_addrs
        : Array.isArray(config.to_addrs)
          ? config.to_addrs.join(', ')
          : typeof config.host === 'string'
            ? config.host
            : '未配置邮箱';
    default:
      return '';
  }
}
