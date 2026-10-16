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

/**
 * 화면 하단 알림(목업 §6 — 어두운 바탕 · 행동 버튼 테두리 · ×). 예: 사람 확인 저장 → "재판정 잡 등록" 제안.
 * 최대 4개, 8초 뒤 닫힘(duration 0 = 직접 닫을 때까지). AppLayout이 한 번 감싼다.
 */
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
        className="pointer-events-none fixed inset-x-0 bottom-10 z-50 flex flex-col items-center gap-2 px-4 sm:items-end sm:px-6 mobile:bottom-28"
      >
        {items.map((item) => (
          <div
            key={item.id}
            role="status"
            aria-live="polite"
            className="pointer-events-auto flex w-full max-w-[460px] items-center gap-3 rounded-xl bg-toast px-3.5 py-3 text-sm text-toast-fg shadow-lg sm:w-auto sm:min-w-[300px]"
          >
            <span className="min-w-0 flex-1">{item.message}</span>
            {item.action ? (
              <button
                type="button"
                className="min-h-8 shrink-0 rounded-lg border border-toast-fg/40 px-2.5 text-[13px] font-semibold text-toast-fg hover:border-toast-fg"
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
              className="inline-flex size-8 shrink-0 items-center justify-center rounded-lg text-lg leading-none text-toast-fg/90 hover:text-toast-fg"
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
