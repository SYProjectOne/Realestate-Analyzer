import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useId, useRef, useState } from 'react';
import {
  clearAuth,
  dismissTokenPrompt,
  releaseTabPin,
  requestToken,
  setAuth,
  useAuth,
  type AuthSnapshot,
} from '@/api/auth';
import { probeToken } from '@/api/client';
import { useToast } from '@/app/toast';
import { Banner } from '@/components/Banner';
import { t, type TKey } from '@/i18n';

/** 지금 토큰 상태 문구(헤더 버튼·다이얼로그) */
export function tokenStateText(auth: AuthSnapshot): string {
  if (!auth.token) return t('auth.state.none');
  if (auth.role === 'read') return t('auth.state.read');
  if (auth.role === 'write') return t('auth.state.write');
  return t('auth.state.unknown');
}

/** 머리줄의 "접속 열쇠 · 상태" 버튼(SH-14: 없음·쓰기 가능·읽기 전용·설정됨) — 누르면 열쇠 창을 연다. */
export function TokenButton() {
  const auth = useAuth();
  return (
    <button
      type="button"
      onClick={() => requestToken('manual')}
      className="min-h-9 whitespace-nowrap rounded-[10px] border border-border-strong bg-surface px-3 py-1.5 text-[13px] font-semibold text-fg hover:border-fg-2 focus:outline-hidden focus-visible:ring-2 focus-visible:ring-accent"
      data-testid="token-button"
      data-token-state={!auth.token ? 'none' : (auth.role ?? 'unknown')}
      aria-haspopup="dialog"
    >
      {t('auth.button')} · {tokenStateText(auth)}
    </button>
  );
}

/** 읽기 전용 토큰이면 전역 안내(쓰기 버튼은 각 화면이 `useCanWrite()`로 끈다). */
export function ReadOnlyBanner() {
  const auth = useAuth();
  if (auth.canWrite) return null;
  return (
    <Banner
      role="note"
      tone="note"
      data-testid="readonly-banner"
      actions={
        <button
          type="button"
          onClick={() => requestToken('manual')}
          className="min-h-10 rounded-[10px] border border-border-strong bg-surface px-3.5 text-sm font-semibold text-fg hover:border-fg-2"
        >
          {t('auth.change')}
        </button>
      }
    >
      {t('auth.readOnlyBanner')}
    </Banner>
  );
}

/**
 * 다른 탭이 저장 토큰을 읽기 전용 토큰으로 바꿔 이 탭이 기존 토큰을 고정해 쓰는 중(N-M7, `auth.externalChange`).
 * "새 토큰 사용" → 고정을 풀고 저장소의 새 토큰으로(모든 쿼리 다시).
 */
export function TokenPinnedBanner() {
  const auth = useAuth();
  const qc = useQueryClient();
  if (!auth.externalChange) return null;
  return (
    <Banner
      role="note"
      tone="note"
      data-testid="token-pinned-banner"
      actions={
        <button
          type="button"
          onClick={() => {
            releaseTabPin();
            void qc.invalidateQueries();
          }}
          className="min-h-10 rounded-[10px] border border-border-strong bg-surface px-3.5 text-sm font-semibold text-fg hover:border-fg-2"
        >
          {t('auth.useNewToken')}
        </button>
      }
    >
      {t('auth.pinnedBanner')}
    </Banner>
  );
}

/**
 * API 토큰 설정 다이얼로그. 열리는 때: API 가 401(토큰 없음·틀림) 또는 헤더 버튼.
 * 저장 = 토큰 확인(`probeToken`: 401 이면 거절, 읽기 전용/쓰기 판별) → localStorage(try/catch, 실패 시 이 탭만) → 모든 쿼리 다시.
 */
export function TokenDialog() {
  const auth = useAuth();
  if (!auth.prompt) return null;
  return <TokenDialogBody auth={auth} />;
}

function TokenDialogBody({ auth }: { auth: AuthSnapshot }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [value, setValue] = useState('');
  const [show, setShow] = useState(false);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const titleId = useId();
  const inputId = useId();
  const reason = auth.prompt ?? 'manual';

  useEffect(() => {
    inputRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') dismissTokenPrompt();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const save = async () => {
    const token = value.trim();
    if (!token) {
      setError(t('auth.empty'));
      return;
    }
    setChecking(true);
    setError(null);
    try {
      const result = await probeToken(token);
      if (result === 'invalid') {
        setError(t('auth.invalid'));
        return;
      }
      const { persisted } = setAuth(token, result);
      const saved = t(result === 'read' ? 'auth.savedRead' : 'auth.savedWrite');
      toast({ message: persisted ? saved : `${saved} · ${t('auth.notPersisted')}` });
      void qc.invalidateQueries();
    } catch (err) {
      setError(t('auth.checkError', { detail: err instanceof Error ? err.message : String(err) }));
    } finally {
      setChecking(false);
    }
  };

  const clear = () => {
    clearAuth();
    toast({ message: t('auth.cleared') });
    void qc.invalidateQueries();
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-overlay/45 p-4"
      data-testid="token-backdrop"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="flex max-h-full w-full max-w-md flex-col gap-3 overflow-y-auto rounded-2xl border border-border-strong bg-surface p-[22px] text-fg shadow-2xl"
      >
        <h2 id={titleId} className="text-lg font-bold">
          {t('auth.title')}
        </h2>
        {/* 열린 이유(SH-13): 401·토큰 필요 = 주의 칸(role=alert), 머리줄 버튼 = 회색 안내 */}
        <p
          role={reason === 'manual' ? undefined : 'alert'}
          data-reason={reason}
          className={`rounded-lg px-2.5 py-2 text-[13px] ${
            reason === 'manual' ? 'bg-subtle text-fg-2' : 'bg-warn-soft font-medium text-warn-ink'
          }`}
        >
          {t(`auth.reason.${reason}` as TKey)}
        </p>
        <p className="text-[13px] leading-relaxed text-fg-2">{t('auth.intro')}</p>
        <p className="text-[13px] text-muted" data-testid="token-current">
          {t('auth.current', { state: tokenStateText(auth) })}
        </p>
        <form
          noValidate
          className="flex flex-col gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            void save();
          }}
        >
          <label htmlFor={inputId} className="text-[13px] font-semibold">
            {t('auth.label')}
          </label>
          <input
            id={inputId}
            ref={inputRef}
            type={show ? 'text' : 'password'}
            value={value}
            autoComplete="off"
            spellCheck={false}
            onChange={(e) => setValue(e.target.value)}
            className="min-h-11 rounded-[10px] border border-border-strong bg-surface px-3 py-2 font-mono text-[15px] text-fg"
          />
          <label className="inline-flex items-center gap-2 text-[13px] text-fg-2">
            <input type="checkbox" checked={show} onChange={(e) => setShow(e.target.checked)} />
            {t('auth.show')}
          </label>
          {error ? (
            <p role="alert" className="text-[13px] text-danger">
              {error}
            </p>
          ) : null}
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="submit"
              disabled={checking}
              className="min-h-11 rounded-[10px] bg-accent px-4 text-sm font-semibold text-accent-fg disabled:opacity-60"
            >
              {checking ? t('auth.checking') : t('auth.save')}
            </button>
            {auth.source === 'storage' || auth.source === 'memory' || auth.source === 'tab' ? (
              <button
                type="button"
                onClick={clear}
                className="min-h-11 rounded-[10px] border border-border-strong bg-surface px-3.5 text-sm font-semibold text-fg"
              >
                {t('auth.clear')}
              </button>
            ) : null}
            <button
              type="button"
              onClick={dismissTokenPrompt}
              className="ml-auto min-h-11 rounded-[10px] border border-border-strong bg-surface px-3.5 text-sm font-semibold text-fg"
            >
              {t('auth.close')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
