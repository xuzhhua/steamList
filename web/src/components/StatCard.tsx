import type { ReactNode } from 'react';
import { Skeleton, cn } from './ui';

export interface StatCardProps {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  icon?: ReactNode;
  tone?: 'accent' | 'good' | 'warn' | 'teal' | 'muted';
  loading?: boolean;
}

const TONE_CLASS: Record<NonNullable<StatCardProps['tone']>, string> = {
  accent: 'text-accent',
  good: 'text-good',
  warn: 'text-warn',
  teal: 'text-teal',
  muted: 'text-ink',
};

export default function StatCard({ label, value, hint, icon, tone = 'muted', loading }: StatCardProps) {
  return (
    <div className="panel px-4 py-3">
      <div className="flex items-center justify-between gap-2 text-[11px] text-muted">
        <span>{label}</span>
        {icon ? <span className={cn('opacity-80', TONE_CLASS[tone])}>{icon}</span> : null}
      </div>
      <div className={cn('num mt-1.5 text-xl font-semibold leading-7', TONE_CLASS[tone])}>
        {loading ? <Skeleton className="h-6 w-16" /> : value}
      </div>
      {hint ? <div className="mt-0.5 truncate text-[11px] text-dim">{hint}</div> : null}
    </div>
  );
}
