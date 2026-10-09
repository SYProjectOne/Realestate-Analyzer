import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { t } from '@/i18n';

export interface ToastAction {
  label: string;
  onClick: () => void;
}

export interface ToastInput {
  message: string;
  action?: ToastAction;
  /** ms. 기본 8초, 0이면 직접 닫을 때까지 */
  duration?: number;
}

interface ToastItem extends ToastInput {
  id: number;
}

type PushToast = (toast: ToastInput) => void;

const ToastContext = createContext<PushToast | null>(null);

/** 화면 하단 알림(예: 사람 확인 저장 → "재판정 잡 등록" 제안). AppLayout이 한 번 감싼다. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const nextId = useRef(1);

  const dismiss = useCallback((id: number) => {
    setItems((prev) => prev.filter((item) => item.id !== id));
  }, []);

  const push = useCallback<PushToast>(
    (toast) => {
      const id = nextId.current++;
      setItems((prev) => [...prev.slice(-3), { ...toast, id }]);
      const duration = toast.duration ?? 8000;
      if (duration > 0) window.setTimeout(() => dismiss(id), duration);
    },
    [dismiss],
  );

  const value = useMemo(() => push, [push]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <section
        aria-label={t('app.notifications')}
        className="pointer-events-none fixed inset-x-0 bottom-10 z-50 flex flex-col items-center gap-2 px-4"
      >
        {items.map((item) => (
          <div
            key={item.id}
            role="status"
            aria-live="polite"
            className="pointer-events-auto flex max-w-lg items-center gap-3 rounded border border-border bg-surface px-3 py-2 text-sm shadow-lg"
          >
            <span>{item.message}</span>
            {item.action ? (
              <button
                type="button"
                className="rounded bg-accent px-2 py-0.5 text-accent-fg"
                onClick={() => {
                  item.action?.onClick();
                  dismiss(item.id);
                }}
              >
                {item.action.label}
              </button>
            ) : null}
            <button
              type="button"
              aria-label={t('app.toastClose')}
              className="ml-auto rounded px-1 text-muted hover:text-fg"
              onClick={() => dismiss(item.id)}
            >
              ×
            </button>
          </div>
        ))}
      </section>
    </ToastContext.Provider>
  );
}

const noop: PushToast = () => {};

/** 알림 띄우기. Provider 밖(단독 렌더 테스트)에서는 아무것도 하지 않는다. */
export function useToast(): PushToast {
  return useContext(ToastContext) ?? noop;
}
