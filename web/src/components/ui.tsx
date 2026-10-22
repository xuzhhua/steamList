import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from 'react';
import { createPortal } from 'react-dom';
import { AlertCircle, AlertTriangle, X } from 'lucide-react';

export function cn(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(' ');
}

/* ---------------------------------- Button --------------------------------- */

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'subtle';
type ButtonSize = 'sm' | 'md' | 'lg' | 'icon';

const BUTTON_VARIANTS: Record<ButtonVariant, string> = {
  primary:
    'bg-accent-strong text-[#04121c] hover:bg-accent font-semibold shadow-[0_0_0_1px_rgba(26,159,255,0.5),0_6px_18px_-8px_rgba(26,159,255,0.7)]',
  secondary: 'border border-line-strong bg-panel-3 text-ink hover:border-accent/60 hover:bg-panel-3/70',
  ghost: 'text-muted hover:bg-white/5 hover:text-ink',
  danger: 'border border-bad/40 bg-bad/10 text-bad hover:bg-bad/20',
  subtle: 'bg-white/5 text-ink hover:bg-white/10',
};

const BUTTON_SIZES: Record<ButtonSize, string> = {
  sm: 'h-8 px-3 text-xs gap-1.5',
  md: 'h-9.5 px-4 text-sm gap-2',
  lg: 'h-11 px-5 text-sm gap-2',
  icon: 'h-9 w-9 justify-center',
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  icon?: ReactNode;
}

export function Button({
  variant = 'secondary',
  size = 'md',
  loading = false,
  icon,
  className,
  children,
  disabled,
  type = 'button',
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      disabled={disabled || loading}
      className={cn(
        'inline-flex select-none items-center justify-center rounded-lg transition-[background-color,border-color,color,box-shadow] duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60 disabled:cursor-not-allowed disabled:opacity-50',
        BUTTON_VARIANTS[variant],
        BUTTON_SIZES[size],
        className,
      )}
      {...rest}
    >
      {loading ? <Spinner size={size === 'sm' ? 12 : 16} /> : icon}
      {children}
    </button>
  );
}

/* ---------------------------------- Panels --------------------------------- */

export function Card({ className, children, ...rest }: { className?: string; children: ReactNode } & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn('panel', className)} {...rest}>
      {children}
    </div>
  );
}

export function SectionHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h2 className="text-base font-semibold text-ink">{title}</h2>
        {description ? <p className="mt-1 text-xs text-muted">{description}</p> : null}
      </div>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
    </div>
  );
}

/* ---------------------------------- Badge ---------------------------------- */

type BadgeTone = 'accent' | 'good' | 'warn' | 'bad' | 'muted' | 'teal';

const BADGE_TONES: Record<BadgeTone, string> = {
  accent: 'bg-accent/12 text-accent border-accent/30',
  good: 'bg-good/12 text-good border-good/30',
  warn: 'bg-warn/12 text-warn border-warn/30',
  bad: 'bg-bad/12 text-bad border-bad/30',
  muted: 'bg-white/5 text-muted border-line',
  teal: 'bg-teal/12 text-teal border-teal/30',
};

export function Badge({ tone = 'muted', className, children }: { tone?: BadgeTone; className?: string; children: ReactNode }) {
  return (
    <span className={cn('inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[11px] font-medium leading-4', BADGE_TONES[tone], className)}>
      {children}
    </span>
  );
}

/* ---------------------------------- Fields --------------------------------- */

export function Label({ children, htmlFor, hint }: { children: ReactNode; htmlFor?: string; hint?: ReactNode }) {
  return (
    <label htmlFor={htmlFor} className="mb-1.5 flex items-baseline justify-between gap-2 text-xs font-medium text-muted">
      <span>{children}</span>
      {hint ? <span className="text-[11px] font-normal text-dim">{hint}</span> : null}
    </label>
  );
}

const FIELD_BASE =
  'w-full rounded-lg border border-line bg-panel-2 px-3 text-sm text-ink placeholder:text-dim transition focus:border-accent/70 focus:outline-none focus:ring-1 focus:ring-accent/40 disabled:opacity-60';

export function Input({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn(FIELD_BASE, 'h-9.5', className)} {...rest} />;
}

export function Textarea({ className, rows = 3, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea rows={rows} className={cn(FIELD_BASE, 'min-h-20 py-2', className)} {...rest} />;
}

export function Select({ className, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={cn(FIELD_BASE, 'h-9.5 appearance-none bg-[length:14px] pr-8', className)} {...rest}>
      {children}
    </select>
  );
}

export function Field({ label, hint, error, children }: { label: string; hint?: ReactNode; error?: string | null; children: ReactNode }) {
  return (
    <div>
      <Label hint={hint}>{label}</Label>
      {children}
      {error ? <p className="mt-1 text-[11px] text-bad">{error}</p> : null}
    </div>
  );
}

/* ---------------------------------- Switch --------------------------------- */

export function Switch({ checked, onChange, disabled, label }: { checked: boolean; onChange: (value: boolean) => void; disabled?: boolean; label?: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        'relative h-5.5 w-10 shrink-0 rounded-full border transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60 disabled:opacity-50',
        checked ? 'border-accent/60 bg-accent/80' : 'border-line-strong bg-panel-3',
      )}
    >
      <span
        className={cn(
          'absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform duration-150',
          checked ? 'translate-x-5' : 'translate-x-0.5',
        )}
      />
    </button>
  );
}

/* -------------------------------- Feedback -------------------------------- */

export function Spinner({ size = 16, className }: { size?: number; className?: string }) {
  return (
    <span
      role="status"
      aria-label="加载中"
      className={cn('inline-block shrink-0 animate-spin rounded-full border-2 border-current border-t-transparent align-middle', className)}
      style={{ width: size, height: size }}
    />
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn('skeleton rounded-md', className)} />;
}

export function SkeletonCard() {
  return (
    <div className="panel overflow-hidden p-3">
      <Skeleton className="aspect-[460/215] w-full" />
      <div className="mt-3 space-y-2">
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="h-3 w-1/2" />
      </div>
    </div>
  );
}

export function ErrorState({ message, onRetry, className }: { message: string; onRetry?: () => void; className?: string }) {
  return (
    <div className={cn('flex flex-col items-center justify-center gap-3 rounded-xl border border-bad/30 bg-bad/5 px-6 py-10 text-center', className)}>
      <AlertCircle size={22} className="text-bad" />
      <p className="text-sm text-ink">{message}</p>
      {onRetry ? (
        <Button size="sm" variant="secondary" onClick={onRetry}>
          重试
        </Button>
      ) : null}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
  icon,
  className,
}: {
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  icon?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn('flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-line-strong bg-panel/40 px-6 py-14 text-center', className)}>
      {icon ? <div className="text-dim">{icon}</div> : null}
      <h3 className="text-sm font-semibold text-ink">{title}</h3>
      {description ? <p className="max-w-md text-xs leading-5 text-muted">{description}</p> : null}
      {action}
    </div>
  );
}

/* ---------------------------------- Modal --------------------------------- */

export function Modal({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  size = 'md',
}: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  description?: ReactNode;
  children?: ReactNode;
  footer?: ReactNode;
  size?: 'sm' | 'md' | 'lg';
}) {
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKeyDown);
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      document.body.style.overflow = previous;
    };
  }, [open, onClose]);

  if (!open) return null;

  const widthClass = size === 'sm' ? 'max-w-sm' : size === 'lg' ? 'max-w-2xl' : 'max-w-lg';

  return createPortal(
    <div className="fixed inset-0 z-[90] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} aria-hidden="true" />
      <div
        role="dialog"
        aria-modal="true"
        className={cn('animate-fade-in relative w-full overflow-hidden rounded-2xl border border-line-strong bg-panel shadow-panel', widthClass)}
      >
        <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
          <div>
            <h3 className="text-sm font-semibold text-ink">{title}</h3>
            {description ? <p className="mt-1 text-xs text-muted">{description}</p> : null}
          </div>
          <button type="button" aria-label="关闭" onClick={onClose} className="rounded p-1 text-dim transition hover:text-ink">
            <X size={16} />
          </button>
        </div>
        {children ? <div className="max-h-[70vh] overflow-y-auto px-5 py-4">{children}</div> : null}
        {footer ? <div className="flex justify-end gap-2 border-t border-line px-5 py-3">{footer}</div> : null}
      </div>
    </div>,
    document.body,
  );
}

/* ------------------------------- ConfirmDialog ------------------------------ */

interface ConfirmOptions {
  title?: string;
  message: ReactNode;
  confirmText?: string;
  cancelText?: string;
  danger?: boolean;
}

const ConfirmContext = createContext<((options: ConfirmOptions) => Promise<boolean>) | null>(null);

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<{ options: ConfirmOptions; resolve: (value: boolean) => void } | null>(null);

  const confirm = useCallback(
    (options: ConfirmOptions) =>
      new Promise<boolean>((resolve) => {
        setState({ options, resolve });
      }),
    [],
  );

  const close = useCallback(
    (value: boolean) => {
      setState((current) => {
        current?.resolve(value);
        return null;
      });
    },
    [],
  );

  const options = state?.options;

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      <Modal
        open={!!state}
        onClose={() => close(false)}
        title={options?.title ?? '请确认'}
        description={options?.message}
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => close(false)}>
              {options?.cancelText ?? '取消'}
            </Button>
            <Button variant={options?.danger ? 'danger' : 'primary'} onClick={() => close(true)}>
              {options?.confirmText ?? '确定'}
            </Button>
          </>
        }
      >
        {options?.danger ? (
          <p className="flex items-center gap-2 text-xs text-warn">
            <AlertTriangle size={14} /> 此操作不可撤销
          </p>
        ) : null}
      </Modal>
    </ConfirmContext.Provider>
  );
}

export function useConfirm() {
  const ctx = useContext(ConfirmContext);
  if (!ctx) throw new Error('useConfirm 必须在 ConfirmProvider 内使用');
  return ctx;
}

/* --------------------------------- Segmented -------------------------------- */

export function Segmented<T extends string>({
  value,
  options,
  onChange,
  className,
}: {
  value: T;
  options: Array<{ value: T; label: string }>;
  onChange: (value: T) => void;
  className?: string;
}) {
  return (
    <div className={cn('inline-flex rounded-lg border border-line bg-panel-2 p-0.5', className)}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          onClick={() => onChange(option.value)}
          className={cn(
            'rounded-md px-2.5 py-1 text-xs transition-colors duration-150',
            option.value === value ? 'bg-accent/15 font-medium text-accent' : 'text-muted hover:text-ink',
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
