import { useEffect, useId, useRef, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router';
import { hasStoredWriteToken, setAuth, setTabAuth } from '@/api/auth';
import { t } from '@/i18n';

/**
 * `#<token>` → token. 비었거나 퍼센트 인코딩이 깨졌으면(decodeURIComponent URIError) null — 토큰 없음으로 안내한다.
 */
export function shareTokenFromHash(hash: string): string | null {
  let token: string;
  try {
    token = decodeURIComponent(hash.replace(/^#/, '')).trim();
  } catch {
    return null;
  }
  return token ? token : null;
}

/** 주소창에서 hash(토큰)를 지운다 — 토큰이 히스토리·화면 공유에 남지 않게 */
function stripHash(): void {
  try {
    window.history.replaceState(
      window.history.state,
      '',
      `${window.location.pathname}${window.location.search}`,
    );
  } catch {
    // 무시 — 아래 navigate 가 라우터 주소를 바꾼다
  }
}

/**
 * `/share#<token>` (M9, 계약 2026-10-09.4) — 읽기 전용 공유 링크로 들어오는 곳.
 * 토큰은 hash 에만 있다(서버 로그·Referer 에 남지 않는다). 주소창에서 hash 를 지운 뒤(history.replaceState) 홈으로 간다.
 * 토큰이 없거나 인코딩이 깨졌으면 안내만 한다.
 *
 * N-M7(R3b): 이 브라우저에 쓰기(또는 권한 모름) 토큰이 저장돼 있거나 빌드 환경변수 토큰(VITE_API_TOKEN)을
 * 쓰는 중이면(R3 3차 minor 16) 조용히 덮어쓰지 않고 묻는다 —
 * "이 탭에서만 읽기 전용으로 보기"(기본, sessionStorage — 저장된 쓰기 토큰·다른 탭은 그대로) ·
 * "저장된 토큰을 공유 토큰으로 바꾸기"(localStorage, 지금까지 동작) · "취소"(적용하지 않고 홈).
 * 저장된 토큰이 없거나 읽기 전용이면 묻지 않고 localStorage 에 읽기 전용으로 저장한다.
 * AppLayout 밖 라우트 — 토큰을 정하기 전에 API 를 부르지 않는다(401 → 토큰 다이얼로그가 뜨지 않게).
 */
export function SharePage() {
  const location = useLocation();
  const navigate = useNavigate();
  const [token] = useState(() => shareTokenFromHash(location.hash || window.location.hash));
  // 처음 열 때 한 번만 판단한다(적용 후 저장소가 바뀌어도 다이얼로그를 다시 띄우지 않게)
  const [confirm] = useState(() => token !== null && hasStoredWriteToken());

  useEffect(() => {
    if (!token) return;
    stripHash();
    if (confirm) return;
    setAuth(token, 'read');
    navigate('/', { replace: true });
  }, [token, confirm, navigate]);

  const done = () => navigate('/', { replace: true });

  return (
    <main className="min-h-screen bg-bg px-4 py-10 text-fg sm:py-16">
      <div className="mx-auto flex max-w-lg flex-col gap-4">
        <p className="text-sm font-bold text-fg-2">{t('app.name')}</p>
        <section className="flex flex-col gap-3 rounded-2xl border border-border bg-surface p-[22px]">
          <h1 className="text-xl font-bold">{t('page.share.title')}</h1>
          {token && confirm ? (
            <ConfirmDialog
              onTabOnly={() => {
                setTabAuth(token, 'read');
                done();
              }}
              onReplace={() => {
                setAuth(token, 'read');
                done();
              }}
              onCancel={done}
            />
          ) : token ? (
            <>
              <p role="status" className="flex items-center gap-2 text-sm text-muted">
                <svg
                  aria-hidden
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.4"
                  strokeLinecap="round"
                  className="shrink-0 animate-spin text-accent motion-reduce:animate-none"
                >
                  <path d="M21 12a9 9 0 1 1-6.2-8.6" />
                </svg>
                {t('page.share.applying')}
              </p>
              <p className="text-[13px] leading-normal text-muted">
                {t('page.share.applyingHint')}
              </p>
            </>
          ) : (
            <>
              <p
                role="alert"
                className="rounded-xl border border-warn-border bg-warn-soft px-3.5 py-3 text-sm leading-relaxed text-warn-ink"
              >
                {t('page.share.missing')}
              </p>
              <Link
                to="/"
                className="inline-flex min-h-11 items-center self-start rounded-[10px] border border-border-strong bg-surface px-4 text-sm font-semibold text-fg hover:border-accent hover:text-accent-ink"
              >
                {t('page.share.home')}
              </Link>
            </>
          )}
        </section>
      </div>
    </main>
  );
}

/** 저장된 쓰기 토큰 덮어쓰기 확인(role=alertdialog). 기본 포커스 = 이 탭에서만, Esc = 취소 */
function ConfirmDialog({
  onTabOnly,
  onReplace,
  onCancel,
}: {
  onTabOnly: () => void;
  onReplace: () => void;
  onCancel: () => void;
}) {
  const titleId = useId();
  const bodyId = useId();
  const defaultRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    defaultRef.current?.focus();
  }, []);
  return (
    <div className="rounded-[14px] bg-overlay/55 px-4 py-6">
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={bodyId}
        onKeyDown={(e) => {
          if (e.key === 'Escape') onCancel();
        }}
        className="mx-auto flex max-w-sm flex-col gap-3 rounded-2xl bg-surface p-5 shadow-xl"
      >
        <h2 id={titleId} className="text-[17px] font-bold leading-snug">
          {t('page.share.confirmTitle')}
        </h2>
        <p id={bodyId} className="text-sm leading-relaxed text-fg-2">
          {t('page.share.confirmBody')}
        </p>
        <div className="flex flex-col gap-2">
          <button
            ref={defaultRef}
            type="button"
            onClick={onTabOnly}
            className="min-h-11 rounded-[10px] bg-accent px-4 text-sm font-semibold text-accent-fg hover:bg-accent-ink focus-visible:ring-2 focus-visible:ring-accent/40 focus-visible:ring-offset-2"
          >
            {t('page.share.tabOnly')}
          </button>
          <button
            type="button"
            onClick={onReplace}
            className="min-h-11 rounded-[10px] border border-border-strong bg-surface px-4 text-sm font-semibold text-fg hover:border-accent"
          >
            {t('page.share.replace')}
          </button>
          <button
            type="button"
            onClick={onCancel}
            className="min-h-11 rounded-[10px] border border-border-strong bg-surface px-4 text-sm font-semibold text-fg hover:border-accent"
          >
            {t('page.share.cancel')}
          </button>
        </div>
        <p className="text-xs leading-normal text-muted">{t('page.share.confirmHint')}</p>
      </div>
    </div>
  );
}
