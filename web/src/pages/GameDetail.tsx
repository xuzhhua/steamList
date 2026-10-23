import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft,
  Bell,
  BellOff,
  CalendarDays,
  ExternalLink,
  History,
  Save,
  Target,
  Trash2,
  TrendingDown,
} from 'lucide-react';
import { api } from '../lib/api';
import type { GameDetailResponse, RangeKey, SeriesResponse, StatsResponse } from '../lib/types';
import {
  centsToInput,
  formatDate,
  formatDateTime,
  formatDays,
  formatDiscount,
  formatIntervalDays,
  formatPercent,
  formatPrice,
  formatRelative,
  inputToCents,
} from '../lib/format';
import { useFetch } from '../hooks/useFetch';
import PriceChart from '../components/PriceChart';
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  Field,
  Input,
  SectionHeader,
  Segmented,
  Skeleton,
  Switch,
  Textarea,
  useConfirm,
} from '../components/ui';
import { useToast } from '../components/toast';

const RANGE_OPTIONS: Array<{ value: RangeKey; label: string }> = [
  { value: '30d', label: '30 天' },
  { value: '90d', label: '90 天' },
  { value: '180d', label: '180 天' },
  { value: '1y', label: '1 年' },
  { value: 'all', label: '全部' },
];

export default function GameDetail() {
  const { appid } = useParams();
  const appidNum = Number(appid);
  const navigate = useNavigate();
  const toast = useToast();
  const confirm = useConfirm();
  const [range, setRange] = useState<RangeKey>('90d');

  const loadDetail = useCallback(() => api.getGame(appidNum), [appidNum]);
  const detail = useFetch<GameDetailResponse>(loadDetail, [appidNum], { enabled: Number.isFinite(appidNum) });

  const loadSeries = useCallback(() => api.getSeries(appidNum, range), [appidNum, range]);
  const series = useFetch<SeriesResponse>(loadSeries, [appidNum, range], {
    enabled: Number.isFinite(appidNum) && !!detail.data,
  });

  const loadStats = useCallback(() => api.getStats(appidNum), [appidNum]);
  const stats = useFetch<StatsResponse>(loadStats, [appidNum], {
    enabled: Number.isFinite(appidNum) && !!detail.data,
  });

  const watch = detail.data?.watch;
  const game = detail.data?.game;

  const [targetPrice, setTargetPrice] = useState('');
  const [threshold, setThreshold] = useState('');
  const [note, setNote] = useState('');
  const [notifyEnabled, setNotifyEnabled] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [imageFailed, setImageFailed] = useState(false);

  useEffect(() => {
    setImageFailed(false);
  }, [game?.header_image]);

  useEffect(() => {
    if (!watch) return;
    setTargetPrice(centsToInput(watch.target_price_cents));
    setThreshold(watch.discount_alert_threshold === null ? '' : String(watch.discount_alert_threshold));
    setNote(watch.note ?? '');
    setNotifyEnabled(watch.notify_enabled);
  }, [watch]);

  const stat = stats.data?.stats;

  const chartPoints = useMemo(() => series.data?.points ?? [], [series.data]);

  if (!Number.isFinite(appidNum)) {
    return <ErrorState message="无效的游戏 AppID" />;
  }

  if (detail.error) {
    return (
      <div className="space-y-4">
        <BackLink />
        <ErrorState message={detail.error} onRetry={() => void detail.reload()} />
      </div>
    );
  }

  if (!detail.data) {
    return (
      <div className="space-y-4">
        <BackLink />
        <Skeleton className="h-44 w-full rounded-xl" />
        <Skeleton className="h-80 w-full rounded-xl" />
      </div>
    );
  }

  if (!game || !watch) {
    return <ErrorState message="未获取到游戏数据" onRetry={() => void detail.reload()} />;
  }

  const save = async () => {
    setSaving(true);
    try {
      await api.patchWatch(appidNum, {
        target_price_cents: inputToCents(targetPrice),
        discount_alert_threshold: threshold.trim() === '' ? null : Number(threshold),
        note,
        notify_enabled: notifyEnabled,
      });
      toast.success('提醒设置已保存');
      await detail.reload();
      await stats.reload();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '保存失败');
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    const ok = await confirm({
      title: '删除关注',
      message: `确定要删除「${game.name}」吗？价格历史会一并删除，且无法恢复。`,
      confirmText: '删除',
      danger: true,
    });
    if (!ok) return;
    setDeleting(true);
    try {
      await api.deleteWatch(appidNum);
      toast.success('已删除关注');
      navigate('/');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '删除失败');
      setDeleting(false);
    }
  };

  const discount = watch.current_discount_percent;

  return (
    <div className="space-y-5">
      <BackLink />

      <Card className="overflow-hidden">
        <div className="grid gap-0 md:grid-cols-[320px_1fr]">
          <div className="relative aspect-[460/215] w-full bg-panel-3 md:aspect-auto md:h-full">
            {game.header_image && !imageFailed ? (
              <img
                src={game.header_image}
                alt={game.name}
                className="h-full w-full object-cover"
                onError={() => setImageFailed(true)}
              />
            ) : (
              <div className="flex h-full min-h-40 items-center justify-center text-2xl font-semibold text-dim">
                {game.name.slice(0, 2)}
              </div>
            )}
            <div className="absolute inset-x-0 top-0 flex justify-between p-2">
              {discount > 0 ? (
                <span className="rounded-md bg-warn px-1.5 py-0.5 text-[11px] font-bold text-[#1a1203]">
                  {formatDiscount(discount)}
                </span>
              ) : (
                <span className="rounded-md bg-black/60 px-1.5 py-0.5 text-[11px] text-muted">未打折</span>
              )}
              {!watch.available ? <Badge tone="muted">当前不可购买</Badge> : null}
            </div>
          </div>

          <div className="flex flex-col gap-4 p-4 sm:p-5">
            <div>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <h1 className="text-lg font-semibold leading-7 text-ink">{game.name}</h1>
                <a
                  href={`https://store.steampowered.com/app/${game.appid}/`}
                  target="_blank"
                  rel="noreferrer"
                  className="focus-ring inline-flex items-center gap-1 rounded-md border border-line px-2 py-1 text-[11px] text-muted transition hover:border-accent/50 hover:text-accent"
                >
                  Steam 商店 <ExternalLink size={11} />
                </a>
              </div>
              {game.short_description ? (
                <p className="mt-2 line-clamp-2 text-xs leading-5 text-muted">{game.short_description}</p>
              ) : null}
              <div className="mt-2 flex flex-wrap gap-1.5">
                {genreChips(game.genres).map((genre) => (
                  <Badge key={genre} tone="muted">
                    {genre}
                  </Badge>
                ))}
                {game.release_date ? <Badge tone="muted">发售 {game.release_date}</Badge> : null}
              </div>
            </div>

            <div className="flex flex-wrap items-end gap-3">
              <span className="num text-2xl font-semibold text-accent">
                {formatPrice(watch.current_final_cents, watch.currency)}
              </span>
              {discount > 0 ? (
                <span className="num pb-1 text-sm text-dim line-through">
                  {formatPrice(watch.current_initial_cents, watch.currency)}
                </span>
              ) : null}
              <span className="pb-1 text-[11px] text-dim">
                最近检查 {formatRelative(watch.last_checked_at)}
              </span>
            </div>

            <div className="grid grid-cols-2 gap-2 border-t border-line pt-3 text-[11px] text-muted sm:grid-cols-4">
              <InfoCell icon={<TrendingDown size={12} className="text-good" />} label="历史最低" value={formatPrice(watch.atl_cents, watch.currency)} />
              <InfoCell icon={<Target size={12} className="text-warn" />} label="目标价" value={watch.target_price_cents !== null ? formatPrice(watch.target_price_cents, watch.currency) : '未设置'} />
              <InfoCell icon={<Bell size={12} className="text-accent" />} label="提醒" value={watch.notify_enabled ? '已开启' : '已关闭'} />
              <InfoCell icon={<CalendarDays size={12} className="text-dim" />} label="记录起点" value={game && watch.record_started_at ? formatDate(watch.record_started_at) : '—'} />
            </div>
          </div>
        </div>
      </Card>

      <Card className="p-4 sm:p-5">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-ink">价格历史</h2>
            <p className="mt-0.5 flex items-center gap-1 text-[11px] text-dim">
              <History size={11} />
              记录起点：{series.data?.record_started_at ? formatDateTime(series.data.record_started_at) : watch.record_started_at ? formatDateTime(watch.record_started_at) : '—'}
            </p>
          </div>
          <Segmented value={range} options={RANGE_OPTIONS} onChange={setRange} />
        </div>

        {series.error ? (
          <ErrorState message={series.error} onRetry={() => void series.reload()} />
        ) : series.loading && chartPoints.length === 0 ? (
          <Skeleton className="h-72 w-full sm:h-80" />
        ) : chartPoints.length === 0 ? (
          <EmptyState title="该区间还没有价格数据" description="价格记录会随每次检查累积，选择一个更长的时间范围试试。" />
        ) : (
          <>
            <PriceChart
              points={chartPoints}
              currency={series.data?.currency ?? watch.currency}
              atlCents={watch.atl_cents}
              recordStartedAt={series.data?.record_started_at ?? watch.record_started_at}
            />
            <p className="mt-2 flex flex-wrap items-center gap-3 text-[11px] text-dim">
              <span className="inline-flex items-center gap-1">
                <span className="inline-block h-2 w-3 rounded-sm bg-accent" /> 现价
              </span>
              <span className="inline-flex items-center gap-1">
                <span className="inline-block h-0.5 w-3 bg-dim" /> 原价（淡线）
              </span>
              <span className="inline-flex items-center gap-1">
                <span className="inline-block h-2 w-3 rounded-sm bg-good/60" /> 历史最低
              </span>
              <span className="inline-flex items-center gap-1">
                <span className="inline-block h-2 w-3 rounded-sm bg-warn/40" /> 打折区间
              </span>
            </p>
          </>
        )}
      </Card>

      <div className="grid gap-5 lg:grid-cols-[1.1fr_1fr]">
        <Card className="p-4 sm:p-5">
          <SectionHeader title="价格统计" description={stats.loading ? '加载中…' : `统计口径基于全部历史记录`} />
          {stats.error ? (
            <ErrorState message={stats.error} onRetry={() => void stats.reload()} />
          ) : (
            <div className="grid grid-cols-2 gap-x-4 gap-y-3 text-xs sm:grid-cols-3">
              <StatItem label="历史最低价" value={stat ? formatPrice(stat.atl_cents, watch.currency) : '—'} />
              <StatItem label="ATL 命中次数" value={stat ? `${stat.atl_hit_count} 次` : '—'} />
              <StatItem label="当前折扣" value={stat ? formatDiscount(stat.current_discount_percent) : '—'} />
              <StatItem label="打折事件数" value={stat ? `${stat.discount_event_count} 次` : '—'} />
              <StatItem label="累计打折天数" value={stat ? formatDays(stat.discount_days) : '—'} />
              <StatItem label="平均折扣" value={stat ? formatPercent(stat.avg_discount_percent) : '—'} />
              <StatItem label="平均间隔" value={stat ? formatIntervalDays(stat.avg_interval_days) : '—'} />
              <StatItem label="最大折扣" value={stat ? formatDiscount(stat.max_discount_percent) : '—'} />
              <StatItem label="价格变化次数" value={stat ? `${stat.change_count} 次` : '—'} />
              <StatItem label="首次记录" value={stats.data?.record_started_at ? formatDate(stats.data.record_started_at) : '—'} />
              <StatItem label="最近变化" value={stat?.last_change_at ? formatDateTime(stat.last_change_at) : '—'} />
              <StatItem label="上次打折" value={stat?.last_discount_at ? formatDate(stat.last_discount_at) : '—'} />
            </div>
          )}
        </Card>

        <Card className="p-4 sm:p-5">
          <SectionHeader title="提醒设置" description="目标价与折扣阈值变化时通过通知通道提醒" />
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <Field label="目标价（元）" hint="留空表示不限制">
                <Input
                  inputMode="decimal"
                  placeholder="例如 98"
                  value={targetPrice}
                  onChange={(event) => setTargetPrice(event.target.value)}
                />
              </Field>
              <Field label="折扣阈值（%）" hint="1–100">
                <Input
                  inputMode="numeric"
                  placeholder="例如 50"
                  value={threshold}
                  onChange={(event) => setThreshold(event.target.value)}
                />
              </Field>
            </div>
            <Field label="备注">
              <Textarea
                rows={2}
                placeholder="例如：等 50% 折扣再买"
                value={note}
                onChange={(event) => setNote(event.target.value)}
              />
            </Field>
            <div className="flex items-center justify-between rounded-lg border border-line bg-panel-2 px-3 py-2.5">
              <div className="flex items-center gap-2 text-xs text-muted">
                {notifyEnabled ? <Bell size={14} className="text-accent" /> : <BellOff size={14} className="text-dim" />}
                开启提醒
              </div>
              <Switch checked={notifyEnabled} onChange={setNotifyEnabled} label="开启提醒" />
            </div>
            <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
              <Button variant="danger" size="sm" icon={<Trash2 size={14} />} loading={deleting} onClick={remove}>
                删除关注
              </Button>
              <Button variant="primary" size="sm" icon={<Save size={14} />} loading={saving} onClick={save}>
                保存设置
              </Button>
            </div>
          </div>
        </Card>
      </div>

      {game.developers || game.publishers ? (
        <p className="text-center text-[11px] text-dim">
          {game.developers ? `开发商：${game.developers}` : ''}
          {game.developers && game.publishers ? ' · ' : ''}
          {game.publishers ? `发行商：${game.publishers}` : ''}
        </p>
      ) : null}
    </div>
  );
}

function genreChips(genres: string): string[] {
  return (genres ?? '')
    .split(',')
    .map((genre) => genre.trim())
    .filter(Boolean)
    .slice(0, 4);
}

function BackLink() {
  return (
    <Link to="/" className="focus-ring inline-flex items-center gap-1.5 text-xs text-muted transition hover:text-ink">
      <ArrowLeft size={14} /> 返回仪表盘
    </Link>
  );
}

function InfoCell({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div className="flex items-center gap-1.5">
      {icon}
      <span className="text-dim">{label}</span>
      <span className="num text-ink">{value}</span>
    </div>
  );
}

function StatItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[11px] text-dim">{label}</div>
      <div className="num mt-0.5 text-sm text-ink">{value}</div>
    </div>
  );
}
