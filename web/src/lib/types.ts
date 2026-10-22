/** 后端 API 数据契约（与 app/schemas.py 保持一致）。金额单位一律为「分」。 */

export interface WatchItem {
  appid: number;
  name: string;
  header_image: string;
  cc: string;
  note: string;
  sort_order: number;
  notify_enabled: boolean;
  target_price_cents: number | null;
  discount_alert_threshold: number | null;
  created_at: string;
  currency: string;
  current_initial_cents: number;
  current_final_cents: number;
  current_discount_percent: number;
  available: boolean;
  atl_cents: number | null;
  atl_hit_count: number;
  atl_last_at: string | null;
  last_checked_at: string | null;
  record_started_at: string | null;
}

export interface WatchSummary {
  count: number;
  discounting_count: number;
  atl_count: number;
  below_target_count: number;
  last_checked_at: string | null;
}

export interface WatchlistResponse {
  items: WatchItem[];
  summary: WatchSummary;
}

export interface SearchItem {
  appid: number;
  name: string;
  header_image: string;
  price_cents: number | null;
  currency: string | null;
}

export interface GameInfo {
  appid: number;
  name: string;
  header_image: string;
  short_description: string;
  developers: string[];
  publishers: string[];
  genres: string[];
  release_date: string;
  is_free: boolean;
}

export interface GameDetailResponse {
  game: GameInfo;
  watch: WatchItem;
}

export type RangeKey = '30d' | '90d' | '180d' | '1y' | 'all';

export interface SeriesPoint {
  t: string;
  final: number;
  initial: number;
  discount: number;
  available: boolean;
}

export interface SeriesResponse {
  appid: number;
  range: RangeKey;
  start: string | null;
  end: string;
  points: SeriesPoint[];
  record_started_at: string | null;
  currency: string;
}

export interface GameStats {
  first_change_at: string | null;
  last_change_at: string | null;
  change_count: number;
  days_tracked: number;
  current_initial_cents: number;
  current_final_cents: number;
  current_discount_percent: number;
  available: boolean;
  atl_cents: number | null;
  atl_first_at: string | null;
  atl_last_at: string | null;
  atl_hit_count: number;
  discount_event_count: number;
  discount_days: number;
  max_discount_percent: number;
  avg_discount_percent: number;
  avg_interval_days: number | null;
  last_discount_at: string | null;
  discounting: boolean;
}

export interface StatsResponse {
  appid: number;
  stats: GameStats;
  record_started_at: string | null;
}

export type ChannelKind = 'bark' | 'email' | 'webhook';

export interface Channel {
  id?: number;
  kind: ChannelKind;
  name: string;
  config: Record<string, unknown>;
  enabled: boolean;
}

export interface Settings {
  poll_enabled: boolean;
  poll_interval_hours: number;
  poll_time: string;
  cc: string;
  lang: string;
  steamid: string;
  proxy_url: string;
  wishlist_enabled: boolean;
  wishlist_last_import_at: string | null;
  next_poll_at: string | null;
  meta_refresh_at: string | null;
  channels: Channel[];
}

export interface ImportResult {
  imported: number;
  skipped: number;
  failed: number;
  total: number;
  appids: number[];
  errors: string[];
}

export interface JobRun {
  id: number;
  job_type: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  checked_count: number;
  changed_count: number;
  error: string | null;
}

export interface JobStatus {
  running: boolean;
  current: JobRun | null;
  last: JobRun | null;
  next_poll_at: string | null;
}

export interface NotificationTestResult {
  channel_id: number | null;
  name: string;
  kind: string;
  ok: boolean;
  error: string | null;
}

export interface NotificationLogItem {
  id: number;
  appid: number | null;
  game_name: string;
  rule: string;
  title: string;
  body: string;
  status: string;
  error: string | null;
  created_at: string;
  sent_at: string | null;
}

export interface BackupItem {
  name: string;
  size_bytes: number;
  created_at: string;
  download_url: string;
}

export interface BackupList {
  backups: BackupItem[];
  latest: BackupItem | null;
}

export interface SteamSession {
  connected: boolean;
  account_name: string;
  steamid: string;
  connected_at: string | null;
}

export interface QrStart {
  session_id: string;
  challenge_url: string;
  interval: number;
  expires_in_seconds: number;
}

export type QrStatusValue = 'pending' | 'scanned' | 'success' | 'expired' | string;

export interface QrStatus {
  status: QrStatusValue;
  account_name: string | null;
  steamid: string | null;
  message: string | null;
}
