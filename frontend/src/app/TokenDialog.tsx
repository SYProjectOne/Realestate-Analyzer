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
import { t, type TKey } from '@/i18n';

/** 지금 토큰 상태 문구(헤더 버튼·다이얼로그) */
export function tokenStateText(auth: AuthSnapshot): string {
  if (!auth.token) return t('auth.state.none');
  if (auth.role === 'read') return t('auth.state.read');
  if (auth.role === 'write') return t('auth.state.write');
  return t('auth.state.unknown');
}

/** 헤더의 "API 토큰" 버튼 — 지금 상태를 보이고 누르면 다이얼로그를 연다. */
export function TokenButton() {
  const auth = useAuth();
  return (
    <button
      type="button"
      onClick={() => requestToken('manual')}
      className="rounded-sm border border-border px-2 py-1 text-xs"
      data-testid="token-button"
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
    <div
      role="note"
      data-testid="readonly-banner"
      className="flex flex-wrap items-center gap-2 border-b border-border bg-surface px-4 py-1.5 text-sm"
    >
      <span>{t('auth.readOnlyBanner')}</span>
      <button type="button" onClick={() => requestToken('manual')} className="text-xs underline">
        {t('auth.change')}
      </button>
    </div>
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
    <div
      role="note"
      data-testid="token-pinned-banner"
      className="flex flex-wrap items-center gap-2 border-b border-border bg-surface px-4 py-1.5 text-sm"
    >
      <span>{t('auth.pinnedBanner')}</span>
      <button
        type="button"
        onClick={() => {
          releaseTabPin();
          void qc.invalidateQueries();
        }}
        className="text-xs underline"
      >
        {t('auth.useNewToken')}
      </button>
    </div>
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="flex w-full max-w-md flex-col gap-3 rounded-sm border border-border bg-surface p-4 text-fg shadow-xl"
      >
        <h2 id={titleId} className="text-base font-semibold">
          {t('auth.title')}
        </h2>
        <p
          role={reason === 'manual' ? undefined : 'alert'}
          className={`text-sm ${reason === 'manual' ? 'text-muted' : 'font-medium text-danger'}`}
        >
          {t(`auth.reason.${reason}` as TKey)}
        </p>
        <p className="text-xs text-muted">{t('auth.intro')}</p>
        <p className="text-xs" data-testid="token-current">
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
          <label htmlFor={inputId} className="text-sm font-medium">
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
            className="rounded-sm border border-border bg-bg px-2 py-1.5 font-mono text-sm"
          />
          <label className="inline-flex items-center gap-1 text-xs text-muted">
            <input type="checkbox" checked={show} onChange={(e) => setShow(e.target.checked)} />
            {t('auth.show')}
          </label>
          {error ? (
            <p role="alert" className="text-sm text-danger">
              {error}
            </p>
          ) : null}
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="submit"
              disabled={checking}
              className="rounded-sm bg-accent px-3 py-1.5 text-sm text-accent-fg disabled:opacity-50"
            >
              {checking ? t('auth.checking') : t('auth.save')}
            </button>
            {auth.source === 'storage' || auth.source === 'memory' || auth.source === 'tab' ? (
              <button
                type="button"
                onClick={clear}
                className="rounded-sm border border-border px-3 py-1.5 text-sm"
              >
                {t('auth.clear')}
              </button>
            ) : null}
            <button
              type="button"
              onClick={dismissTokenPrompt}
              className="ml-auto rounded-sm border border-border px-3 py-1.5 text-sm"
            >
              {t('auth.close')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
