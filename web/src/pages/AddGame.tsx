import { useCallback, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  CheckCircle2,
  Download,
  Hash,
  Info,
  Plus,
  Search,
  SlidersHorizontal,
  XCircle,
} from 'lucide-react';
import { api } from '../lib/api';
import type { ImportResult, SearchItem, Settings, WatchlistResponse } from '../lib/types';
import { formatPrice } from '../lib/format';
import { useDebounce } from '../hooks/useDebounce';
import { useFetch } from '../hooks/useFetch';
import { Badge, Button, Card, EmptyState, ErrorState, Field, Input, SectionHeader, Skeleton, Textarea } from '../components/ui';
import { useToast } from '../components/toast';

export default function AddGame() {
  const toast = useToast();
  const [term, setTerm] = useState('');
  const debouncedTerm = useDebounce(term.trim(), 400);
  const [showOptions, setShowOptions] = useState(false);
  const [targetPrice, setTargetPrice] = useState('');
  const [threshold, setThreshold] = useState('');
  const [note, setNote] = useState('');
  const [adding, setAdding] = useState<number | null>(null);
  const [appidInput, setAppidInput] = useState('');
  const [steamid, setSteamid] = useState('');
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<ImportResult | null>(null);
  const [added, setAdded] = useState<number[]>([]);

  const loadWatchlist = useCallback(() => api.getWatchlist(), []);
  const watchlist = useFetch<WatchlistResponse>(loadWatchlist, []);
  const loadSettings = useCallback(() => api.getSettings(), []);
  useFetch<Settings>(loadSettings, [], {
    enabled: true,
  });

  const loadSearch = useCallback(() => api.searchGames(debouncedTerm), [debouncedTerm]);
  const search = useFetch<{ items: SearchItem[] }>(loadSearch, [debouncedTerm], {
    enabled: debouncedTerm.length >= 2,
  });

  const watchedAppids = useMemo(() => {
    const set = new Set(watchlist.data?.items.map((item) => item.appid) ?? []);
    added.forEach((appid) => set.add(appid));
    return set;
  }, [watchlist.data, added]);

  const buildOptions = () => {
    const options: { target_price_cents?: number | null; discount_alert_threshold?: number | null; note?: string } = {};
    const price = targetPrice.trim();
    if (price) {
      const cents = Math.round(Number(price) * 100);
      if (Number.isFinite(cents) && cents >= 0) options.target_price_cents = cents;
    }
    const thresholdValue = threshold.trim();
    if (thresholdValue) {
      const value = Number(thresholdValue);
      if (Number.isInteger(value) && value >= 1 && value <= 100) options.discount_alert_threshold = value;
    }
    if (note.trim()) options.note = note.trim();
    return options;
  };

  const addGame = async (appid: number, name?: string) => {
    setAdding(appid);
    try {
      const created = await api.addWatch({ appid, ...buildOptions() });
      setAdded((list) => [...list, appid]);
      toast.success(name ? `已关注「${created.name}」` : `已添加 AppID ${appid}`);
      await watchlist.reload();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '添加失败');
    } finally {
      setAdding(null);
    }
  };

  const addByAppid = async () => {
    const appid = Number(appidInput.trim());
    if (!Number.isInteger(appid) || appid <= 0) {
      toast.error('请输入正确的 AppID（正整数）');
      return;
    }
    await addGame(appid);
    setAppidInput('');
  };

  const importWishlist = async () => {
    setImporting(true);
    setImportResult(null);
    try {
      const result = await api.importWishlist(steamid.trim() ? { steamid: steamid.trim() } : {});
      setImportResult(result);
      toast.success(`导入完成：新增 ${result.imported} 款`);
      await watchlist.reload();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '导入失败');
    } finally {
      setImporting(false);
    }
  };

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-lg font-semibold text-ink">添加游戏</h1>
        <p className="mt-1 text-xs text-muted">搜索 Steam 商店、直接输入 AppID，或从 Steam 心愿单批量导入。</p>
      </div>

      <Card className="p-4 sm:p-5">
        <SectionHeader
          title="搜索游戏"
          description="输入至少 2 个字符，支持中英文名称"
          actions={
            <Button
              size="sm"
              variant="ghost"
              icon={<SlidersHorizontal size={14} />}
              onClick={() => setShowOptions((value) => !value)}
            >
              {showOptions ? '收起添加选项' : '添加选项'}
            </Button>
          }
        />
        <div className="relative">
          <Search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-dim" />
          <Input
            autoFocus
            className="pl-9"
            placeholder="例如：Hades / 只狼 / 艾尔登法环"
            value={term}
            onChange={(event) => setTerm(event.target.value)}
          />
        </div>

        {showOptions ? (
          <div className="mt-3 grid gap-3 rounded-lg border border-line bg-panel-2 p-3 sm:grid-cols-3">
            <Field label="目标价（元）" hint="可选">
              <Input inputMode="decimal" placeholder="例如 98" value={targetPrice} onChange={(event) => setTargetPrice(event.target.value)} />
            </Field>
            <Field label="折扣阈值（%）" hint="1–100">
              <Input inputMode="numeric" placeholder="例如 50" value={threshold} onChange={(event) => setThreshold(event.target.value)} />
            </Field>
            <Field label="备注">
              <Textarea rows={1} className="min-h-9.5 py-2" placeholder="可选" value={note} onChange={(event) => setNote(event.target.value)} />
            </Field>
          </div>
        ) : null}

        <div className="mt-4 space-y-2">
          {debouncedTerm.length < 2 ? (
            <p className="flex items-center gap-1.5 text-xs text-dim">
              <Info size={13} /> 输入两个字符以上开始搜索
            </p>
          ) : search.loading && !search.data ? (
            <div className="space-y-2">
              <Skeleton className="h-16 w-full" />
              <Skeleton className="h-16 w-full" />
            </div>
          ) : search.error ? (
            <ErrorState message={search.error} onRetry={() => void search.reload()} />
          ) : (search.data?.items.length ?? 0) === 0 ? (
            <EmptyState title="没有找到匹配的游戏" description="换个关键词试试，或直接输入 AppID 添加。" />
          ) : (
            <ul className="divide-y divide-line overflow-hidden rounded-lg border border-line">
              {search.data?.items.map((item) => {
                const isWatched = watchedAppids.has(item.appid);
                return (
                  <li key={item.appid} className="flex items-center gap-3 bg-panel-2/60 px-3 py-2">
                    <img
                      src={item.header_image}
                      alt=""
                      loading="lazy"
                      className="h-12 w-24 shrink-0 rounded object-cover"
                    />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm text-ink">{item.name}</p>
                      <p className="text-[11px] text-dim">
                        AppID {item.appid}
                        {item.price_cents !== null ? ` · ${formatPrice(item.price_cents, item.currency ?? 'CNY')}` : ''}
                      </p>
                    </div>
                    {isWatched ? (
                      <div className="flex items-center gap-2">
                        <Badge tone="good">
                          <CheckCircle2 size={11} /> 已关注
                        </Badge>
                        <Link
                          to={`/games/${item.appid}`}
                          className="focus-ring rounded-md border border-line px-2 py-1 text-[11px] text-muted transition hover:border-accent/50 hover:text-accent"
                        >
                          详情
                        </Link>
                      </div>
                    ) : (
                      <Button
                        size="sm"
                        variant="primary"
                        icon={<Plus size={13} />}
                        loading={adding === item.appid}
                        onClick={() => void addGame(item.appid, item.name)}
                      >
                        添加
                      </Button>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </Card>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card className="p-4 sm:p-5">
          <SectionHeader title="通过 AppID 添加" description="已知商店页面地址中的数字 ID 时最快" />
          <div className="flex items-end gap-2">
            <div className="flex-1">
              <Field label="AppID">
                <Input
                  inputMode="numeric"
                  placeholder="例如 1145360"
                  value={appidInput}
                  onChange={(event) => setAppidInput(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') void addByAppid();
                  }}
                />
              </Field>
            </div>
            <Button variant="primary" icon={<Hash size={14} />} loading={adding !== null} onClick={() => void addByAppid()}>
              添加
            </Button>
          </div>
          <p className="mt-2 text-[11px] leading-5 text-dim">
            商店链接形如 <span className="num">store.steampowered.com/app/1145360</span>，其中 1145360 即 AppID。
          </p>
        </Card>

        <Card className="p-4 sm:p-5">
          <SectionHeader
            title="从 Steam 心愿单导入"
            description="支持 SteamID64、个人资料链接或自定义链接名；在「设置」中扫码登录后可导入私密心愿单"
          />
          <div className="flex items-end gap-2">
            <div className="flex-1">
              <Field label="SteamID / 个人资料链接 / 自定义链接名" hint="可选">
                <Input
                  placeholder="7656119… 或 steamcommunity.com/id/xxx"
                  value={steamid}
                  onChange={(event) => setSteamid(event.target.value)}
                />
              </Field>
            </div>
            <Button variant="secondary" icon={<Download size={14} />} loading={importing} onClick={() => void importWishlist()}>
              导入
            </Button>
          </div>

          {importResult ? (
            <div className="mt-3 space-y-2 rounded-lg border border-line bg-panel-2 p-3 text-xs">
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-muted">
                <span>
                  总计 <span className="num text-ink">{importResult.total}</span>
                </span>
                <span className="text-good">
                  新增 <span className="num">{importResult.imported}</span>
                </span>
                <span>
                  已存在 <span className="num">{importResult.skipped}</span>
                </span>
                <span className={importResult.failed > 0 ? 'text-bad' : ''}>
                  失败 <span className="num">{importResult.failed}</span>
                </span>
              </div>
              {importResult.errors.length > 0 ? (
                <ul className="max-h-32 space-y-0.5 overflow-y-auto text-[11px] text-bad">
                  {importResult.errors.map((message, index) => (
                    <li key={index} className="flex items-start gap-1">
                      <XCircle size={11} className="mt-0.5 shrink-0" /> {message}
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : (
            <p className="mt-2 text-[11px] leading-5 text-dim">
              留空则使用「设置」中保存的 SteamID。导入会跳过已关注的游戏。
              未连接 Steam 账号时只能读取公开心愿单：若提示不可见，请到「设置 → Steam 账号」扫码登录，或把 Steam 隐私设置中的「我的个人资料」设为「公开」。
            </p>
          )}
        </Card>
      </div>
    </div>
  );
}
