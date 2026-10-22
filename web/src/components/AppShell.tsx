import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { LayoutDashboard, PlusCircle, RefreshCw, Settings as SettingsIcon, Gamepad2 } from 'lucide-react';
import { useJobStatus } from '../hooks/useJobStatus';
import { formatRelative } from '../lib/format';
import { useToast } from './toast';
import { Spinner } from './ui';

const NAV = [
  { to: '/', label: '仪表盘', icon: LayoutDashboard, end: true },
  { to: '/add', label: '添加游戏', icon: PlusCircle, end: false },
  { to: '/settings', label: '设置', icon: SettingsIcon, end: false },
];

function Brand() {
  return (
    <div className="flex items-center gap-2.5">
      <span className="flex h-9 w-9 items-center justify-center rounded-lg border border-accent/30 bg-accent/10 text-accent">
        <Gamepad2 size={18} />
      </span>
      <span className="leading-tight">
        <span className="block text-sm font-semibold tracking-wide text-ink">SteamList</span>
        <span className="block text-[11px] text-dim">Steam 价格追踪</span>
      </span>
    </div>
  );
}

function JobIndicator() {
  const toast = useToast();
  const { status, startRefresh, starting } = useJobStatus(5000);
  const running = starting || status?.running;
  const last = status?.last;
  const current = status?.current;

  const onRefresh = async () => {
    try {
      const ok = await startRefresh();
      if (ok) toast.info('已开始检查价格，稍后自动更新');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '触发刷新失败');
    }
  };

  return (
    <div className="flex items-center gap-2">
      <div className="hidden text-right text-[11px] leading-4 text-dim sm:block">
        {current
          ? '正在检查价格…'
          : last?.finished_at
            ? `上次检查 ${formatRelative(last.finished_at)}`
            : '尚未检查过'}
      </div>
      <button
        type="button"
        onClick={onRefresh}
        disabled={running}
        title="立即刷新价格"
        className="focus-ring inline-flex h-9 items-center gap-2 rounded-lg border border-line-strong bg-panel-3 px-3 text-xs text-ink transition hover:border-accent/60 disabled:opacity-60"
      >
        {running ? <Spinner size={14} className="text-accent" /> : <RefreshCw size={14} />}
        <span className="hidden sm:inline">{running ? '刷新中' : '刷新价格'}</span>
      </button>
    </div>
  );
}

export default function AppShell() {
  const location = useLocation();

  return (
    <div className="flex min-h-full">
      {/* 桌面侧边栏 */}
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-line bg-panel-2/60 px-4 py-5 backdrop-blur md:flex">
        <Brand />
        <nav className="mt-8 flex flex-col gap-1">
          {NAV.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors duration-150 ${
                    isActive
                      ? 'bg-accent/12 font-medium text-accent'
                      : 'text-muted hover:bg-white/5 hover:text-ink'
                  }`
                }
              >
                <Icon size={16} />
                {item.label}
              </NavLink>
            );
          })}
        </nav>
        <div className="mt-auto space-y-1 border-t border-line pt-4 text-[11px] leading-5 text-dim">
          <p>自托管 · 数据保存在本机</p>
          <p>金额单位：人民币元</p>
        </div>
      </aside>

      {/* 主内容区 */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-40 border-b border-line bg-base/85 backdrop-blur">
          <div className="mx-auto flex h-14 w-full max-w-7xl items-center justify-between gap-3 px-4 sm:px-6">
            <div className="flex items-center gap-3 md:hidden">
              <Brand />
            </div>
            <div className="hidden items-baseline gap-2 md:flex">
              <span className="text-sm font-medium text-ink">
                {location.pathname === '/'
                  ? '仪表盘'
                  : location.pathname === '/add'
                    ? '添加游戏'
                    : location.pathname === '/settings'
                      ? '设置'
                      : '游戏详情'}
              </span>
              <span className="text-[11px] text-dim">价格历史 · 历史低价 · 提醒</span>
            </div>
            <JobIndicator />
          </div>
        </header>

        <main className="mx-auto w-full max-w-7xl flex-1 px-4 pb-24 pt-5 sm:px-6 md:pb-10">
          <Outlet />
        </main>
      </div>

      {/* 移动端底部导航 */}
      <nav className="fixed inset-x-0 bottom-0 z-40 border-t border-line bg-panel-2/95 backdrop-blur md:hidden">
        <div className="mx-auto flex max-w-md items-stretch justify-around">
          {NAV.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `flex flex-1 flex-col items-center gap-1 py-2.5 text-[11px] transition-colors ${
                    isActive ? 'text-accent' : 'text-dim'
                  }`
                }
              >
                <Icon size={18} />
                {item.label}
              </NavLink>
            );
          })}
        </div>
      </nav>
    </div>
  );
}
