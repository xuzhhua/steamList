import { useCallback, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowDownWideNarrow,
  Gamepad2,
  History,
  Plus,
  RefreshCw,
  Target,
  TrendingDown,
  Tag,
} from 'lucide-react';
import { api } from '../lib/api';
import type { WatchlistResponse, WatchItem } from '../lib/types';
import { formatDateTime } from '../lib/format';
import { useFetch } from '../hooks/useFetch';
import { useJobStatus } from '../hooks/useJobStatus';
import GameCard from '../components/GameCard';
import StatCard from '../components/StatCard';
import { Button, EmptyState, ErrorState, Segmented, Select, SkeletonCard, Spinner } from '../components/ui';
import { useToast } from '../components/toast';

type FilterKey = 'all' | 'discounting' | 'below_target';
type SortKey = 'discount' | 'drop' | 'name' | 'updated';

const FILTER_OPTIONS: Array<{ value: FilterKey; label: string }> = [
  { value: 'all', label: '全部' },
  { value: 'discounting', label: '打折中' },
  { value: 'below_target', label: '低于目标价' },
];

const SORT_OPTIONS: Array<{ value: SortKey; label: string }> = [
  { value: 'discount', label: '折扣从高到低' },
  { value: 'drop', label: '降价幅度从大到小' },
  { value: 'name', label: '名称 A→Z' },
  { value: 'updated', label: '最近更新优先' },
];

function filterItems(items: WatchItem[], filter: FilterKey): WatchItem[] {
  if (filter === 'discounting') return items.filter((item) => item.current_discount_percent > 0);
  if (filter === 'below_target') {
    return items.filter(
      (item) => item.target_price_cents !== null && item.current_final_cents <= item.target_price_cents,
    );
  }
  return items;
}

function sortItems(items: WatchItem[], sort: SortKey): WatchItem[] {
  const copy = [...items];
  switch (sort) {
    case 'discount':
      copy.sort((a, b) => b.current_discount_percent - a.current_discount_percent || a.name.localeCompare(b.name, 'zh'));
      break;
    case 'drop':
      copy.sort(
        (a, b) =>
          (b.current_initial_cents - b.current_final_cents) - (a.current_initial_cents - a.current_final_cents) ||
          a.name.localeCompare(b.name, 'zh'),
      );
      break;
    case 'name':
      copy.sort((a, b) => a.name.localeCompare(b.name, 'zh'));
      break;
    case 'updated':
      copy.sort((a, b) => (b.last_checked_at ?? '').localeCompare(a.last_checked_at ?? ''));
      break;
  }
  return copy;
}

export default function Dashboard() {
  const toast = useToast();
  const loadWatchlist = useCallback(() => api.getWatchlist(), []);
  const { data, error, loading, reload } = useFetch<WatchlistResponse>(loadWatchlist, []);
  const { status, startRefresh, starting } = useJobStatus(4000);
  const [filter, setFilter] = useState<FilterKey>('all');
  const [sort, setSort] = useState<SortKey>('discount');

  const items = data?.items ?? [];
  const summary = data?.summary;

  const visible = useMemo(() => sortItems(filterItems(items, filter), sort), [items, filter, sort]);

  const running = starting || status?.running;
  const current = status?.current;

  const refresh = async () => {
    try {
      const ok = await startRefresh();
      if (ok) {
        toast.info('已开始检查价格，完成后面板会自动更新');
        window.setTimeout(() => {
          void reload();
        }, 1500);
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '触发刷新失败');
    }
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-ink">价格仪表盘</h1>
          <p className="mt-1 text-xs text-muted">
            {summary?.last_checked_at ? `上次检查：${formatDateTime(summary.last_checked_at)}` : '还没有价格检查记录'}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link
            to="/add"
            className="focus-ring inline-flex h-9.5 items-center gap-2 rounded-lg bg-accent-strong px-4 text-sm font-semibold text-[#04121c] transition hover:bg-accent"
          >
            <Plus size={16} /> 添加游戏
          </Link>
          <Button variant="secondary" loading={running} icon={<RefreshCw size={16} />} onClick={refresh}>
            {running ? '检查中…' : '刷新价格'}
          </Button>
        </div>
      </div>

      {running ? (
        <div className="flex items-center gap-2 rounded-xl border border-accent/30 bg-accent/5 px-4 py-2.5 text-xs text-accent">
          <Spinner size={14} />
          <span>
            正在检查价格{current ? `，已检查 ${current.checked_count} 款，其中 ${current.changed_count} 款有变化` : '…'}
          </span>
        </div>
      ) : null}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard
          label="关注总数"
          value={summary?.count ?? 0}
          hint="已加入追踪的游戏"
          icon={<Gamepad2 size={14} />}
          tone="accent"
          loading={loading}
        />
        <StatCard
          label="打折中"
          value={summary?.discounting_count ?? 0}
          hint="当前有折扣"
          icon={<Tag size={14} />}
          tone="warn"
          loading={loading}
        />
        <StatCard
          label="历史低价命中"
          value={summary?.atl_count ?? 0}
          hint="当前正处于历史最低价"
          icon={<TrendingDown size={14} />}
          tone="good"
          loading={loading}
        />
        <StatCard
          label="低于目标价"
          value={summary?.below_target_count ?? 0}
          hint="已到你设定的价位"
          icon={<Target size={14} />}
          tone="teal"
          loading={loading}
        />
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <Segmented value={filter} options={FILTER_OPTIONS} onChange={setFilter} />
        <div className="flex items-center gap-2 text-xs text-muted">
          <ArrowDownWideNarrow size={14} className="text-dim" />
          <Select
            aria-label="排序方式"
            value={sort}
            onChange={(event) => setSort(event.target.value as SortKey)}
            className="h-8 w-44 text-xs"
          >
            {SORT_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
        </div>
      </div>

      {error ? (
        <ErrorState message={error} onRetry={() => void reload()} />
      ) : loading && items.length === 0 ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <SkeletonCard key={index} />
          ))}
        </div>
      ) : items.length === 0 ? (
        <EmptyState
          icon={<Gamepad2 size={30} />}
          title="还没有关注任何游戏"
          description="添加想要追踪的游戏，SteamList 会定时记录价格变化、计算历史最低价，并在打折或到达目标价时提醒你。"
          action={
            <Link
              to="/add"
              className="focus-ring inline-flex h-9 items-center gap-2 rounded-lg bg-accent-strong px-4 text-sm font-semibold text-[#04121c] transition hover:bg-accent"
            >
              <Plus size={16} /> 去添加游戏
            </Link>
          }
        />
      ) : visible.length === 0 ? (
        <EmptyState title="当前筛选下没有游戏" description="换一个筛选条件看看，或添加新的关注。" />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {visible.map((item) => (
            <GameCard key={item.appid} item={item} />
          ))}
        </div>
      )}

      {items.length > 0 ? (
        <p className="flex items-center justify-center gap-1.5 pt-2 text-[11px] text-dim">
          <History size={12} /> 共 {items.length} 款游戏，卡片上的日期为价格记录起点
        </p>
      ) : null}

      {data?.summary?.last_checked_at ? (
        <p className="text-center text-[11px] text-dim">价格数据每 {25} 小时自动更新一次</p>
      ) : null}
    </div>
  );
}
