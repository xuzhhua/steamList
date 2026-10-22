import { Link } from 'react-router-dom';
import { Compass } from 'lucide-react';

export default function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-24 text-center">
      <Compass size={32} className="text-dim" />
      <h1 className="text-lg font-semibold text-ink">页面不存在</h1>
      <p className="text-xs text-muted">你访问的地址可能已被移除，或输入有误。</p>
      <Link
        to="/"
        className="focus-ring mt-2 inline-flex h-9 items-center rounded-lg bg-accent-strong px-4 text-sm font-semibold text-[#04121c] transition hover:bg-accent"
      >
        返回仪表盘
      </Link>
    </div>
  );
}
