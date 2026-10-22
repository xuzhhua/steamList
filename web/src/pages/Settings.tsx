import { useCallback, useEffect, useState } from 'react';
import {
  Bell,
  Clock,
  Database,
  Download,
  FileArchive,
  History,
  ListChecks,
  Plus,
  RefreshCw,
  Save,
  Send,
  Server,
  Trash2,
  X,
} from 'lucide-react';
import { api, backupDownloadUrl } from '../lib/api';
import type {
  BackupList,
  Channel,
  ChannelKind,
  JobRun,
  NotificationLogItem,
  Settings,
} from '../lib/types';
import { formatBytes, formatDateTime, statusLabel } from '../lib/format';
import { useFetch } from '../hooks/useFetch';
import { useJobStatus } from '../hooks/useJobStatus';
import {
  Badge,
  Button,
  Card,
  ErrorState,
  Field,
  Input,
  SectionHeader,
  Select,
  Skeleton,
  Switch,
  Textarea,
  useConfirm,
} from '../components/ui';
import { useToast } from '../components/toast';

const KIND_LABEL: Record<ChannelKind, string> = {
  bark: 'Bark',
  email: '邮件',
  webhook: 'Webhook',
};

const LANG_OPTIONS = [
  { value: 'schinese', label: '简体中文' },
  { value: 'tchinese', label: '繁体中文' },
  { value: 'english', label: 'English' },
  { value: 'japanese', label: '日本語' },
  { value: 'russian', label: 'Русский' },
];

const CC_OPTIONS = [
  { value: 'cn', label: '中国（CNY）' },
  { value: 'us', label: '美国（USD）' },
  { value: 'eu', label: '欧元区（EUR）' },
  { value: 'de', label: '德国（EUR）' },
  { value: 'gb', label: '英国（GBP）' },
  { value: 'jp', label: '日本（JPY）' },
  { value: 'kr', label: '韩国（KRW）' },
  { value: 'ru', label: '俄罗斯（RUB）' },
  { value: 'br', label: '巴西（BRL）' },
  { value: 'tr', label: '土耳其（TRY）' },
  { value: 'in', label: '印度（INR）' },
];

interface FormState {
  poll_enabled: boolean;
  poll_interval_hours: string;
  poll_time: string;
  cc: string;
  lang: string;
  steamid: string;
  proxy_url: string;
  wishlist_enabled: boolean;
}

interface ChannelDraft {
  key: string;
  id?: number;
  kind: ChannelKind;
  name: string;
  enabled: boolean;
  url: string;
  sound: string;
  icon: string;
  method: string;
  headersText: string;
  host: string;
  port: string;
  from_addr: string;
  to_addrs: string;
  use_ssl: boolean;
  use_tls: boolean;
  username: string;
  password: string;
}

function asString(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

let draftSeq = 0;
function nextKey(): string {
  draftSeq += 1;
  return `draft-${draftSeq}`;
}

function fromChannel(channel: Channel): ChannelDraft {
  const config = channel.config ?? {};
  const toAddrs = Array.isArray(config.to_addrs)
    ? config.to_addrs.map((value) => String(value)).join(', ')
    : asString(config.to_addrs);
  return {
    key: nextKey(),
    id: channel.id,
    kind: channel.kind,
    name: channel.name ?? '',
    enabled: channel.enabled,
    url: asString(config.url),
    sound: asString(config.sound),
    icon: asString(config.icon),
    method: asString(config.method) || 'POST',
    headersText:
      config.headers && typeof config.headers === 'object' ? JSON.stringify(config.headers, null, 2) : '',
    host: asString(config.host),
    port: config.port !== undefined && config.port !== null ? String(config.port) : '465',
    from_addr: asString(config.from_addr),
    to_addrs: toAddrs,
    use_ssl: config.use_ssl !== false,
    use_tls: config.use_tls === true,
    username: asString(config.username),
    password: asString(config.password),
  };
}

function blankChannel(kind: ChannelKind): ChannelDraft {
  return {
    key: nextKey(),
    kind,
    name: KIND_LABEL[kind],
    enabled: true,
    url: '',
    sound: '',
    icon: '',
    method: 'POST',
    headersText: '',
    host: '',
    port: '465',
    from_addr: '',
    to_addrs: '',
    use_ssl: true,
    use_tls: false,
    username: '',
    password: '',
  };
}

function toChannel(draft: ChannelDraft): Channel {
  let config: Record<string, unknown>;
  if (draft.kind === 'bark') {
    config = { url: draft.url.trim() };
    if (draft.sound.trim()) config.sound = draft.sound.trim();
    if (draft.icon.trim()) config.icon = draft.icon.trim();
  } else if (draft.kind === 'webhook') {
    config = { url: draft.url.trim(), method: draft.method };
    if (draft.headersText.trim()) {
      try {
        const parsed: unknown = JSON.parse(draft.headersText);
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
          config.headers = parsed;
        } else {
          throw new Error('请求头必须是 JSON 对象');
        }
      } catch (err) {
        throw new Error(`Webhook 自定义请求头不是合法 JSON：${err instanceof Error ? err.message : '解析失败'}`);
      }
    }
  } else {
    config = {
      host: draft.host.trim(),
      port: Number(draft.port) || (draft.use_ssl ? 465 : 587),
      from_addr: draft.from_addr.trim(),
      to_addrs: draft.to_addrs
        .split(',')
        .map((part) => part.trim())
        .filter(Boolean),
      use_ssl: draft.use_ssl,
      use_tls: draft.use_tls,
    };
    if (draft.username.trim()) config.username = draft.username.trim();
    if (draft.password) config.password = draft.password;
  }

  return {
    ...(draft.id !== undefined ? { id: draft.id } : {}),
    kind: draft.kind,
    name: draft.name.trim() || KIND_LABEL[draft.kind],
    config,
    enabled: draft.enabled,
  };
}

function validateChannel(draft: ChannelDraft): string | null {
  if (!draft.name.trim()) return '请填写通道名称';
  if (draft.kind === 'bark' && !draft.url.trim()) return 'Bark 通道需要填写推送地址 URL';
  if (draft.kind === 'webhook' && !draft.url.trim()) return 'Webhook 通道需要填写回调 URL';
  if (draft.kind === 'email') {
    if (!draft.host.trim()) return '邮件通道需要填写 SMTP 服务器';
    if (!draft.from_addr.trim()) return '邮件通道需要填写发件人地址';
    if (!draft.to_addrs.trim()) return '邮件通道需要填写收件人地址';
  }
  return null;
}

export default function SettingsPage() {
  const toast = useToast();
  const confirm = useConfirm();
  const loadSettings = useCallback(() => api.getSettings(), []);
  const { data, error, loading, reload } = useFetch<Settings>(loadSettings, []);
  const [form, setForm] = useState<FormState | null>(null);
  const [channels, setChannels] = useState<ChannelDraft[]>([]);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState<number | 'all' | null>(null);

  useEffect(() => {
    if (!data) return;
    setForm({
      poll_enabled: data.poll_enabled,
      poll_interval_hours: String(data.poll_interval_hours),
      poll_time: data.poll_time,
      cc: data.cc,
      lang: data.lang,
      steamid: data.steamid ?? '',
      proxy_url: data.proxy_url ?? '',
      wishlist_enabled: data.wishlist_enabled,
    });
    setChannels(data.channels.map(fromChannel));
  }, [data]);

  const save = async () => {
    if (!form) return;
    const interval = Number(form.poll_interval_hours);
    if (!Number.isInteger(interval) || interval < 1 || interval > 168) {
      toast.error('轮询间隔需为 1–168 的整数小时');
      return;
    }
    if (!/^\d{2}:\d{2}$/.test(form.poll_time)) {
      toast.error('请填写有效的轮询时间（HH:MM）');
      return;
    }
    for (const channel of channels) {
      const problem = validateChannel(channel);
      if (problem) {
        toast.error(`${KIND_LABEL[channel.kind]}「${channel.name || '未命名'}」：${problem}`);
        return;
      }
    }
    setSaving(true);
    try {
      let payloadChannels: Channel[];
      try {
        payloadChannels = channels.map(toChannel);
      } catch (err) {
        toast.error(err instanceof Error ? err.message : '通道配置格式不正确');
        return;
      }
      const payload: Partial<Settings> = {
        poll_enabled: form.poll_enabled,
        poll_interval_hours: interval,
        poll_time: form.poll_time,
        cc: form.cc.trim(),
        lang: form.lang.trim(),
        steamid: form.steamid.trim(),
        proxy_url: form.proxy_url.trim(),
        wishlist_enabled: form.wishlist_enabled,
        channels: payloadChannels,
      };
      await api.putSettings(payload);
      toast.success('设置已保存');
      await reload();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '保存失败');
    } finally {
      setSaving(false);
    }
  };

  const testChannel = async (channel: ChannelDraft) => {
    if (channel.id === undefined) {
      toast.info('请先保存设置，再测试该通道');
      return;
    }
    setTesting(channel.id);
    try {
      const result = await api.testNotification(channel.id);
      const item = result.results[0];
      if (item?.ok) toast.success(`「${item.name}」测试消息发送成功`);
      else toast.error(`「${item?.name ?? channel.name}」测试失败：${item?.error ?? '未知错误'}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '测试失败');
    } finally {
      setTesting(null);
    }
  };

  const testAll = async () => {
    setTesting('all');
    try {
      const result = await api.testNotification();
      const failed = result.results.filter((item) => !item.ok);
      if (result.results.length === 0) toast.info('还没有可测试的通知通道');
      else if (failed.length === 0) toast.success(`已向 ${result.results.length} 个通道发送测试消息`);
      else toast.error(`${failed.length} 个通道测试失败：${failed.map((item) => item.name).join('、')}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '测试失败');
    } finally {
      setTesting(null);
    }
  };

  const removeChannel = async (channel: ChannelDraft) => {
    const ok = await confirm({
      title: '删除通知通道',
      message: `确定删除「${channel.name || KIND_LABEL[channel.kind]}」吗？保存设置后生效。`,
      danger: true,
      confirmText: '删除',
    });
    if (!ok) return;
    setChannels((list) => list.filter((item) => item.key !== channel.key));
  };

  const updateChannel = (key: string, patch: Partial<ChannelDraft>) => {
    setChannels((list) => list.map((item) => (item.key === key ? { ...item, ...patch } : item)));
  };

  if (loading && !form) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-48 w-full rounded-xl" />
        <Skeleton className="h-64 w-full rounded-xl" />
      </div>
    );
  }

  if (error) {
    return <ErrorState message={error} onRetry={() => void reload()} />;
  }

  if (!form) return null;

  return (
    <div className="space-y-5 pb-16">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-ink">设置</h1>
          <p className="mt-1 text-xs text-muted">轮询、通知、任务与备份管理，保存后立即生效。</p>
        </div>
        <Button variant="primary" icon={<Save size={15} />} loading={saving} onClick={() => void save()}>
          保存设置
        </Button>
      </div>

      <Card className="p-4 sm:p-5">
        <SectionHeader title="价格轮询" description="按固定间隔检查关注游戏的价格与折扣" />
        <div className="grid gap-4 sm:grid-cols-3">
          <div className="flex items-center justify-between rounded-lg border border-line bg-panel-2 px-3 py-2.5 sm:col-span-1">
            <div className="flex items-center gap-2 text-xs text-muted">
              <Clock size={14} className="text-accent" /> 自动轮询
            </div>
            <Switch
              checked={form.poll_enabled}
              onChange={(value) => setForm({ ...form, poll_enabled: value })}
              label="自动轮询"
            />
          </div>
          <Field label="轮询间隔（小时）" hint="1–168">
            <Input
              inputMode="numeric"
              value={form.poll_interval_hours}
              onChange={(event) => setForm({ ...form, poll_interval_hours: event.target.value })}
            />
          </Field>
          <Field label="每日轮询时间">
            <Input
              type="time"
              value={form.poll_time}
              onChange={(event) => setForm({ ...form, poll_time: event.target.value })}
            />
          </Field>
        </div>
        <p className="mt-3 text-[11px] text-dim">
          下次自动轮询：{data?.next_poll_at ? formatDateTime(data.next_poll_at) : '未安排（轮询已关闭）'}
        </p>
      </Card>

      <Card className="p-4 sm:p-5">
        <SectionHeader title="商店与心愿单" description="价格查询使用的国家/语言，以及 Steam 账号信息" />
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="商店国家">
            <Select value={form.cc} onChange={(event) => setForm({ ...form, cc: event.target.value })}>
              {CC_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="商店语言">
            <Select value={form.lang} onChange={(event) => setForm({ ...form, lang: event.target.value })}>
              {LANG_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="SteamID / 个人资料链接 / 自定义链接名" hint="导入心愿单用，需要公开的个人资料">
            <Input
              value={form.steamid}
              placeholder="7656119… 或 steamcommunity.com/id/xxx"
              onChange={(event) => setForm({ ...form, steamid: event.target.value })}
            />
          </Field>
          <Field label="代理地址" hint="可选，例如 http://127.0.0.1:7890">
            <Input
              value={form.proxy_url}
              placeholder="留空表示直连"
              onChange={(event) => setForm({ ...form, proxy_url: event.target.value })}
            />
          </Field>
        </div>
        <div className="mt-3 flex items-center justify-between rounded-lg border border-line bg-panel-2 px-3 py-2.5">
          <div className="flex items-center gap-2 text-xs text-muted">
            <Download size={14} className="text-accent" /> 允许从心愿单导入
          </div>
          <Switch
            checked={form.wishlist_enabled}
            onChange={(value) => setForm({ ...form, wishlist_enabled: value })}
            label="允许从心愿单导入"
          />
        </div>
        <p className="mt-2 text-[11px] text-dim">
          上次导入：{data?.wishlist_last_import_at ? formatDateTime(data.wishlist_last_import_at) : '从未导入'}
        </p>
      </Card>

      <Card className="p-4 sm:p-5">
        <SectionHeader
          title="通知通道"
          description="价格到达目标价或折扣达到阈值时推送提醒"
          actions={
            <>
              <Button size="sm" variant="ghost" icon={<Send size={14} />} loading={testing === 'all'} onClick={() => void testAll()}>
                全部测试
              </Button>
              <Button
                size="sm"
                variant="secondary"
                icon={<Plus size={14} />}
                onClick={() => setChannels((list) => [...list, blankChannel('bark')])}
              >
                添加通道
              </Button>
            </>
          }
        />
        {channels.length === 0 ? (
          <p className="flex items-center gap-1.5 text-xs text-dim">
            <Bell size={13} /> 还没有通知通道，添加 Bark / 邮件 / Webhook 后即可接收提醒。
          </p>
        ) : (
          <div className="space-y-3">
            {channels.map((channel) => (
              <div key={channel.key} className="rounded-lg border border-line bg-panel-2 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Select
                    aria-label="通道类型"
                    value={channel.kind}
                    onChange={(event) => updateChannel(channel.key, { kind: event.target.value as ChannelKind })}
                    className="h-8 w-28 text-xs"
                  >
                    {(Object.keys(KIND_LABEL) as ChannelKind[]).map((kind) => (
                      <option key={kind} value={kind}>
                        {KIND_LABEL[kind]}
                      </option>
                    ))}
                  </Select>
                  <Input
                    aria-label="通道名称"
                    value={channel.name}
                    placeholder="通道名称"
                    onChange={(event) => updateChannel(channel.key, { name: event.target.value })}
                    className="h-8 w-40 text-xs"
                  />
                  {channel.id !== undefined ? <Badge tone="muted">#{channel.id}</Badge> : <Badge tone="warn">未保存</Badge>}
                  <div className="ml-auto flex items-center gap-2">
                    <Switch
                      checked={channel.enabled}
                      onChange={(value) => updateChannel(channel.key, { enabled: value })}
                      label="启用通道"
                    />
                    <Button
                      size="sm"
                      variant="ghost"
                      icon={<Send size={13} />}
                      loading={testing === channel.id}
                      onClick={() => void testChannel(channel)}
                    >
                      测试
                    </Button>
                    <Button size="icon" variant="ghost" aria-label="删除通道" onClick={() => void removeChannel(channel)}>
                      <Trash2 size={14} className="text-bad" />
                    </Button>
                  </div>
                </div>

                <div className="mt-3 grid gap-3 sm:grid-cols-2">
                  {channel.kind === 'bark' ? (
                    <>
                      <Field label="Bark 推送地址（必填）">
                        <Input value={channel.url} placeholder="https://api.day.app/xxx" onChange={(event) => updateChannel(channel.key, { url: event.target.value })} />
                      </Field>
                      <div className="grid grid-cols-2 gap-3">
                        <Field label="提示音">
                          <Input value={channel.sound} placeholder="可选" onChange={(event) => updateChannel(channel.key, { sound: event.target.value })} />
                        </Field>
                        <Field label="图标">
                          <Input value={channel.icon} placeholder="可选" onChange={(event) => updateChannel(channel.key, { icon: event.target.value })} />
                        </Field>
                      </div>
                    </>
                  ) : null}

                  {channel.kind === 'webhook' ? (
                    <>
                      <Field label="回调 URL（必填）">
                        <Input value={channel.url} placeholder="https://example.com/webhook" onChange={(event) => updateChannel(channel.key, { url: event.target.value })} />
                      </Field>
                      <Field label="请求方法">
                        <Select value={channel.method} onChange={(event) => updateChannel(channel.key, { method: event.target.value })}>
                          <option value="POST">POST</option>
                          <option value="PUT">PUT</option>
                          <option value="PATCH">PATCH</option>
                        </Select>
                      </Field>
                      <div className="sm:col-span-2">
                        <Field label="自定义请求头（JSON，可选）" hint='例如 {"Authorization": "Bearer xxx"}'>
                          <Textarea
                            rows={2}
                            className="min-h-16 font-mono text-xs"
                            value={channel.headersText}
                            placeholder="留空则不添加自定义请求头"
                            onChange={(event) => updateChannel(channel.key, { headersText: event.target.value })}
                          />
                        </Field>
                      </div>
                    </>
                  ) : null}

                  {channel.kind === 'email' ? (
                    <>
                      <Field label="SMTP 服务器（必填）">
                        <Input value={channel.host} placeholder="smtp.example.com" onChange={(event) => updateChannel(channel.key, { host: event.target.value })} />
                      </Field>
                      <Field label="端口">
                        <Input inputMode="numeric" value={channel.port} onChange={(event) => updateChannel(channel.key, { port: event.target.value })} />
                      </Field>
                      <Field label="发件人（必填）">
                        <Input value={channel.from_addr} placeholder="notify@example.com" onChange={(event) => updateChannel(channel.key, { from_addr: event.target.value })} />
                      </Field>
                      <Field label="收件人（必填）" hint="多个用逗号分隔">
                        <Input value={channel.to_addrs} placeholder="me@example.com" onChange={(event) => updateChannel(channel.key, { to_addrs: event.target.value })} />
                      </Field>
                      <Field label="用户名">
                        <Input value={channel.username} placeholder="可选" onChange={(event) => updateChannel(channel.key, { username: event.target.value })} />
                      </Field>
                      <Field label="密码 / 授权码">
                        <Input type="password" value={channel.password} placeholder="可选" onChange={(event) => updateChannel(channel.key, { password: event.target.value })} />
                      </Field>
                      <div className="flex items-center gap-4 sm:col-span-2">
                        <label className="flex items-center gap-2 text-xs text-muted">
                          <Switch checked={channel.use_ssl} onChange={(value) => updateChannel(channel.key, { use_ssl: value })} label="使用 SSL" />
                          使用 SSL
                        </label>
                        <label className="flex items-center gap-2 text-xs text-muted">
                          <Switch checked={channel.use_tls} onChange={(value) => updateChannel(channel.key, { use_tls: value })} label="使用 TLS" />
                          使用 TLS
                        </label>
                      </div>
                    </>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      <div className="grid gap-5 lg:grid-cols-2">
        <JobPanel />
        <BackupPanel />
      </div>

      <NotificationLogPanel />

      <div className="flex justify-end">
        <Button variant="primary" icon={<Save size={15} />} loading={saving} onClick={() => void save()}>
          保存设置
        </Button>
      </div>
    </div>
  );
}

function JobPanel() {
  const toast = useToast();
  const { status, startRefresh, starting } = useJobStatus(5000);
  const current = status?.current;
  const last = status?.last;

  const refresh = async () => {
    try {
      const ok = await startRefresh();
      if (ok) toast.info('已开始检查价格');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '触发刷新失败');
    }
  };

  return (
    <Card className="p-4 sm:p-5">
      <SectionHeader
        title="任务状态"
        description="价格检查任务的运行情况"
        actions={
          <Button size="sm" variant="secondary" icon={<RefreshCw size={14} />} loading={starting || !!status?.running} onClick={() => void refresh()}>
            立即检查
          </Button>
        }
      />
      <div className="space-y-2 text-xs">
        <div className="flex items-center justify-between">
          <span className="text-muted">当前状态</span>
          <Badge tone={status?.running ? 'accent' : 'muted'}>{status?.running ? '检查进行中' : '空闲'}</Badge>
        </div>
        {current ? (
          <div className="rounded-lg border border-accent/25 bg-accent/5 px-3 py-2 text-accent">
            已检查 {current.checked_count} 款 · 有变化 {current.changed_count} 款
          </div>
        ) : null}
        <div className="flex items-center justify-between">
          <span className="text-muted">下次自动检查</span>
          <span className="num text-ink">{status?.next_poll_at ? formatDateTime(status.next_poll_at) : '未安排'}</span>
        </div>
        <RunRow label="上次任务" run={last} />
      </div>
    </Card>
  );
}

function RunRow({ label, run }: { label: string; run: JobRun | null | undefined }) {
  if (!run) {
    return (
      <div className="flex items-center justify-between">
        <span className="text-muted">{label}</span>
        <span className="text-dim">暂无记录</span>
      </div>
    );
  }
  return (
    <div className="space-y-1 rounded-lg border border-line bg-panel-2 px-3 py-2">
      <div className="flex items-center justify-between">
        <span className="text-muted">{label}</span>
        <Badge tone={run.status === 'error' ? 'bad' : 'muted'}>{statusLabel(run.status)}</Badge>
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-dim">
        <span>开始 {run.started_at ? formatDateTime(run.started_at) : '—'}</span>
        <span>结束 {run.finished_at ? formatDateTime(run.finished_at) : '—'}</span>
        <span>
          检查 {run.checked_count} · 变化 {run.changed_count}
        </span>
      </div>
      {run.error ? <p className="text-[11px] text-bad">错误：{run.error}</p> : null}
    </div>
  );
}

function BackupPanel() {
  const toast = useToast();
  const confirm = useConfirm();
  const load = useCallback(() => api.listBackups(), []);
  const { data, error, loading, reload } = useFetch<BackupList>(load, []);
  const [creating, setCreating] = useState(false);

  const create = async () => {
    setCreating(true);
    try {
      await api.createBackup();
      toast.success('备份已创建');
      await reload();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '创建备份失败');
    } finally {
      setCreating(false);
    }
  };

  const confirmDownload = async (name: string) => {
    const ok = await confirm({
      title: '下载备份',
      message: `将下载备份文件「${name}」，浏览器会直接开始下载。`,
      confirmText: '下载',
    });
    if (!ok) return;
    window.location.href = backupDownloadUrl(name);
  };

  return (
    <Card className="p-4 sm:p-5">
      <SectionHeader
        title="数据备份"
        description="备份数据库文件，建议定期下载保存"
        actions={
          <Button size="sm" variant="secondary" icon={<Database size={14} />} loading={creating} onClick={() => void create()}>
            立即备份
          </Button>
        }
      />
      {error ? (
        <ErrorState message={error} onRetry={() => void reload()} />
      ) : loading && !data ? (
        <Skeleton className="h-16 w-full" />
      ) : (data?.backups.length ?? 0) === 0 ? (
        <p className="flex items-center gap-1.5 text-xs text-dim">
          <FileArchive size={13} /> 还没有备份文件，点击「立即备份」创建。
        </p>
      ) : (
        <ul className="divide-y divide-line overflow-hidden rounded-lg border border-line">
          {data?.backups.slice(0, 6).map((backup) => (
            <li key={backup.name} className="flex items-center gap-3 bg-panel-2/60 px-3 py-2 text-xs">
              <FileArchive size={14} className="shrink-0 text-dim" />
              <div className="min-w-0 flex-1">
                <p className="truncate font-mono text-[11px] text-ink">{backup.name}</p>
                <p className="text-[11px] text-dim">
                  {formatBytes(backup.size_bytes)} · {formatDateTime(backup.created_at)}
                </p>
              </div>
              {data?.latest?.name === backup.name ? <Badge tone="good">最新</Badge> : null}
              <Button size="sm" variant="ghost" icon={<Download size={13} />} onClick={() => void confirmDownload(backup.name)}>
                下载
              </Button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function NotificationLogPanel() {
  const [limit, setLimit] = useState(20);
  const load = useCallback(() => api.getNotificationLog(limit), [limit]);
  const { data, error, loading, reload } = useFetch<{ items: NotificationLogItem[] }>(load, [limit]);

  const tone = (status: string) => (status === 'sent' ? 'good' : status === 'error' ? 'bad' : 'muted');

  return (
    <Card className="p-4 sm:p-5">
      <SectionHeader
        title="通知日志"
        description="最近的提醒发送记录"
        actions={
          <>
            <Select
              aria-label="日志条数"
              value={String(limit)}
              onChange={(event) => setLimit(Number(event.target.value))}
              className="h-8 w-24 text-xs"
            >
              <option value="20">20 条</option>
              <option value="50">50 条</option>
              <option value="100">100 条</option>
            </Select>
            <Button size="sm" variant="ghost" icon={<History size={14} />} onClick={() => void reload()}>
              刷新
            </Button>
          </>
        }
      />
      {error ? (
        <ErrorState message={error} onRetry={() => void reload()} />
      ) : loading && !data ? (
        <Skeleton className="h-24 w-full" />
      ) : (data?.items.length ?? 0) === 0 ? (
        <p className="flex items-center gap-1.5 text-xs text-dim">
          <ListChecks size={13} /> 暂无通知记录。
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-left text-xs">
            <thead>
              <tr className="border-b border-line text-[11px] text-dim">
                <th className="py-2 pr-3 font-normal">时间</th>
                <th className="py-2 pr-3 font-normal">游戏</th>
                <th className="py-2 pr-3 font-normal">规则</th>
                <th className="py-2 pr-3 font-normal">标题</th>
                <th className="py-2 pr-3 font-normal">状态</th>
              </tr>
            </thead>
            <tbody>
              {data?.items.map((item) => (
                <tr key={item.id} className="border-b border-line/60 last:border-0">
                  <td className="num whitespace-nowrap py-2 pr-3 text-dim">{formatDateTime(item.created_at)}</td>
                  <td className="py-2 pr-3 text-ink">{item.game_name || (item.appid !== null ? `AppID ${item.appid}` : '—')}</td>
                  <td className="py-2 pr-3 text-muted">{item.rule}</td>
                  <td className="max-w-[280px] truncate py-2 pr-3 text-muted" title={item.body}>
                    {item.title}
                  </td>
                  <td className="py-2 pr-3">
                    <Badge tone={tone(item.status)}>{statusLabel(item.status)}</Badge>
                    {item.error ? (
                      <span className="ml-2 text-[11px] text-bad" title={item.error}>
                        <X size={11} className="inline" />
                      </span>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="mt-2 flex items-center gap-1 text-[11px] text-dim">
        <Server size={11} /> 通知由后端按轮询结果自动发送
      </p>
    </Card>
  );
}
