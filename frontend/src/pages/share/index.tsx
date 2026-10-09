import { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router';
import { setAuth } from '@/api/auth';
import { t } from '@/i18n';

/** `#<token>` → token. 빈 문자열이면 null */
export function shareTokenFromHash(hash: string): string | null {
  const token = decodeURIComponent(hash.replace(/^#/, '')).trim();
  return token ? token : null;
}

/**
 * `/share#<token>` (M9, 계약 2026-10-09.4) — 읽기 전용 공유 링크로 들어오는 곳.
 * 토큰은 hash 에만 있다(서버 로그·Referer 에 남지 않는다). 읽기 전용 토큰으로 저장하고, 주소창에서 hash 를
 * 지운 뒤(history.replaceState) 홈으로 간다. 토큰이 없으면 안내만 한다.
 * AppLayout 밖 라우트 — 토큰을 저장하기 전에 API 를 부르지 않는다(401 → 토큰 다이얼로그가 뜨지 않게).
 */
export function SharePage() {
  const location = useLocation();
  const navigate = useNavigate();
  const [token] = useState(() => shareTokenFromHash(location.hash || window.location.hash));

  useEffect(() => {
    if (!token) return;
    setAuth(token, 'read');
    try {
      window.history.replaceState(
        window.history.state,
        '',
        `${window.location.pathname}${window.location.search}`,
      );
    } catch {
      // 무시 — 아래 navigate 가 라우터 주소를 바꾼다
    }
    navigate('/', { replace: true });
  }, [token, navigate]);

  return (
    <main className="mx-auto flex min-h-screen max-w-lg flex-col gap-3 bg-bg p-6 text-fg">
      <h1 className="text-xl font-semibold">{t('page.share.title')}</h1>
      {token ? (
        <p role="status" className="text-sm text-muted">
          {t('page.share.applying')}
        </p>
      ) : (
        <>
          <p role="alert" className="text-sm text-danger">
            {t('page.share.missing')}
          </p>
          <Link to="/" className="text-sm underline">
            {t('page.share.home')}
          </Link>
        </>
      )}
    </main>
  );
}
