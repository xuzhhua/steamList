import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react';
import { AlertTriangle, CheckCircle2, Info, X } from 'lucide-react';

export type ToastKind = 'success' | 'error' | 'info';

interface ToastItem {
  id: number;
  kind: ToastKind;
  message: string;
}

interface ToastApi {
  push: (message: string, kind?: ToastKind) => void;
  success: (message: string) => void;
  error: (message: string) => void;
  info: (message: string) => void;
}

const ToastContext = createContext<ToastApi | null>(null);

const TONE: Record<ToastKind, { icon: ReactNode; className: string }> = {
  success: { icon: <CheckCircle2 size={18} className="text-good" />, className: 'border-good/40' },
  error: { icon: <AlertTriangle size={18} className="text-bad" />, className: 'border-bad/40' },
  info: { icon: <Info size={18} className="text-accent" />, className: 'border-accent/40' },
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const nextId = useRef(1);

  const remove = useCallback((id: number) => {
    setItems((list) => list.filter((item) => item.id !== id));
  }, []);

  const push = useCallback(
    (message: string, kind: ToastKind = 'info') => {
      const id = nextId.current;
      nextId.current += 1;
      setItems((list) => [...list, { id, kind, message }]);
      window.setTimeout(() => remove(id), 4200);
    },
    [remove],
  );

  const api = useMemo<ToastApi>(
    () => ({
      push,
      success: (message: string) => push(message, 'success'),
      error: (message: string) => push(message, 'error'),
      info: (message: string) => push(message, 'info'),
    }),
    [push],
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="pointer-events-none fixed inset-x-0 bottom-4 z-[100] flex flex-col items-center gap-2 px-4 sm:bottom-6 sm:left-auto sm:right-6 sm:items-end">
        {items.map((item) => {
          const tone = TONE[item.kind];
          return (
            <div
              key={item.id}
              role="status"
              className={`animate-slide-in pointer-events-auto flex w-full max-w-sm items-center gap-3 rounded-xl border bg-panel-3/95 px-4 py-3 text-sm text-ink shadow-panel backdrop-blur ${tone.className}`}
            >
              {tone.icon}
              <span className="min-w-0 flex-1 break-words">{item.message}</span>
              <button
                type="button"
                aria-label="关闭提示"
                onClick={() => remove(item.id)}
                className="rounded p-1 text-dim transition hover:text-ink"
              >
                <X size={14} />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast 必须在 ToastProvider 内使用');
  return ctx;
}
