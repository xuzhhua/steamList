/** 金额（整数分）、时间、数字格式化工具。 */

const CURRENCY_SYMBOLS: Record<string, string> = {
  CNY: '¥',
  USD: '$',
  EUR: '€',
  GBP: '£',
  JPY: '¥',
  KRW: '₩',
  RUB: '₽',
  BRL: 'R$',
  TRY: '₺',
  INR: '₹',
};

export function currencySymbol(currency?: string | null): string {
  if (!currency) return '';
  return CURRENCY_SYMBOLS[currency.toUpperCase()] ?? '';
}

/** 分 -> 金额字符串。整数价格不显示小数，否则保留两位。 */
export function formatPrice(cents?: number | null, currency?: string | null): string {
  if (cents === null || cents === undefined) return '—';
  const value = cents / 100;
  const symbol = currencySymbol(currency);
  const num = Number.isInteger(value) ? String(value) : value.toFixed(2);
  return symbol ? `${symbol}${num}` : num;
}

/** 分 -> 纯数字（用于输入框回填）。 */
export function centsToInput(cents: number | null | undefined): string {
  if (cents === null || cents === undefined) return '';
  return String(cents / 100);
}

/** 输入框里的「元」-> 整数分；非法返回 null。 */
export function inputToCents(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const num = Number(trimmed);
  if (!Number.isFinite(num) || num < 0) return null;
  return Math.round(num * 100);
}

export function formatDiscount(percent: number | null | undefined): string {
  if (!percent || percent <= 0) return '—';
  return `-${Math.round(percent)}%`;
}

export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return `${Math.round(value * 100) / 100}%`;
}

function pad(n: number): string {
  return n < 10 ? `0${n}` : String(n);
}

/** ISO 时间 -> 本地时区 "YYYY-MM-DD HH:mm"。 */
export function formatDateTime(iso?: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function formatDate(iso?: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function formatShortDateTime(iso?: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** 相对时间，用于「最近更新」。 */
export function formatRelative(iso?: string | null): string {
  if (!iso) return '从未';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  const diff = Date.now() - d.getTime();
  if (diff < 0) return formatShortDateTime(iso);
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return '刚刚';
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} 天前`;
  return formatDate(iso);
}

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  let value = bytes;
  let idx = 0;
  while (value >= 1024 && idx < units.length - 1) {
    value /= 1024;
    idx += 1;
  }
  return `${value >= 100 || idx === 0 ? Math.round(value) : value.toFixed(1)} ${units[idx]}`;
}

export function formatDays(days: number | null | undefined): string {
  if (days === null || days === undefined) return '—';
  if (Number.isInteger(days)) return `${days} 天`;
  return `${days.toFixed(2)} 天`;
}

export function formatIntervalDays(days: number | null | undefined): string {
  if (days === null || days === undefined) return '—';
  return `${Math.round(days * 10) / 10} 天`;
}

export function statusLabel(status: string): string {
  switch (status) {
    case 'running':
      return '进行中';
    case 'success':
    case 'ok':
      return '成功';
    case 'error':
    case 'failed':
      return '失败';
    case 'sent':
      return '已发送';
    case 'pending':
      return '待发送';
    case 'skipped':
      return '已跳过';
    default:
      return status;
  }
}
