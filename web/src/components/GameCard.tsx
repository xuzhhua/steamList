import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Bell, BellOff, Target, TrendingDown, History } from 'lucide-react';
import type { WatchItem } from '../lib/types';
import { formatDate, formatDiscount, formatPrice, formatRelative } from '../lib/format';

export default function GameCard({ item }: { item: WatchItem }) {
  const [imageFailed, setImageFailed] = useState(false);
  const discount = item.current_discount_percent;
  const belowTarget = item.target_price_cents !== null && item.current_final_cents <= item.target_price_cents;

  useEffect(() => {
    setImageFailed(false);
  }, [item.header_image]);

  return (
    <Link
      to={`/games/${item.appid}`}
      className="panel panel-hover group block overflow-hidden"
    >
      <div className="relative aspect-[460/215] w-full overflow-hidden bg-panel-3">
        {item.header_image && !imageFailed ? (
          <img
            src={item.header_image}
            alt={item.name}
            loading="lazy"
            onError={() => setImageFailed(true)}
            className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.03]"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center bg-gradient-to-br from-panel-3 to-panel-2 text-2xl font-semibold text-dim">
            {item.name.slice(0, 2)}
          </div>
        )}
        <div className="absolute inset-x-0 top-0 flex items-start justify-between p-2">
          {discount > 0 ? (
            <span className="rounded-md bg-warn px-1.5 py-0.5 text-[11px] font-bold text-[#1a1203] shadow">
              {formatDiscount(discount)}
            </span>
          ) : (
            <span className="rounded-md bg-black/55 px-1.5 py-0.5 text-[11px] text-muted">未打折</span>
          )}
          {item.notify_enabled ? (
            <Bell size={14} className="text-accent/80" aria-label="提醒已开启" />
          ) : (
            <BellOff size={14} className="text-dim" aria-label="提醒已关闭" />
          )}
        </div>
        {!item.available ? (
          <div className="absolute inset-x-0 bottom-0 flex items-center justify-center bg-black/60 py-1 text-[11px] text-muted">
            当前渠道不可购买
          </div>
        ) : null}
      </div>

      <div className="space-y-2 p-3">
        <div className="flex items-start justify-between gap-2">
          <h3 className="line-clamp-2 min-h-[2.5rem] flex-1 text-sm font-medium leading-5 text-ink">{item.name}</h3>
          <span className="shrink-0 rounded bg-white/5 px-1.5 py-0.5 text-[10px] uppercase text-dim">{item.cc}</span>
        </div>

        <div className="flex items-end gap-2">
          <span className="num text-lg font-semibold leading-6 text-accent">{formatPrice(item.current_final_cents, item.currency)}</span>
          {discount > 0 ? (
            <span className="num pb-0.5 text-xs text-dim line-through">{formatPrice(item.current_initial_cents, item.currency)}</span>
          ) : null}
        </div>

        <div className="grid grid-cols-2 gap-1.5 border-t border-line pt-2 text-[11px] text-muted">
          <span className="flex items-center gap-1" title="历史最低价">
            <TrendingDown size={12} className="text-good" />
            <span className="num">{formatPrice(item.atl_cents, item.currency)}</span>
          </span>
          <span className="flex items-center justify-end gap-1" title="价格记录起点">
            <History size={12} className="text-dim" />
            <span className="num">{item.record_started_at ? formatDate(item.record_started_at) : '—'}</span>
          </span>
          <span className="flex items-center gap-1" title="目标价">
            <Target size={12} className={belowTarget ? 'text-warn' : 'text-dim'} />
            <span className={`num ${belowTarget ? 'text-warn' : ''}`}>
              {item.target_price_cents !== null ? formatPrice(item.target_price_cents, item.currency) : '未设置'}
            </span>
          </span>
          <span className="flex items-center justify-end gap-1 text-dim" title="最近检查时间">
            {formatRelative(item.last_checked_at)}
          </span>
        </div>

        {item.note ? (
          <p className="line-clamp-1 text-[11px] text-dim" title={item.note}>
            {item.note}
          </p>
        ) : null}
      </div>
    </Link>
  );
}
