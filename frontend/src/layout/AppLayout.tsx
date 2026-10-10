import { Suspense } from 'react';
import { Outlet } from 'react-router';
import { DegradedBanner } from '@/app/DegradedBanner';
import { ReadOnlyBanner, TokenDialog, TokenPinnedBanner } from '@/app/TokenDialog';
import { ToastProvider } from '@/app/toast';
import { useProvenanceSnapshot } from '@/components/provenanceContext';
import { useMobileLayout } from '@/hooks/useMobileLayout';
import { useSnapshot } from '@/hooks/useSnapshot';
import { t } from '@/i18n';
import { Header } from './Header';

/** 하단 고정 문구 — D7 "모든 판정 화면 하단에 투자 권유 아님 · 상대 비교". 전 화면에 둔다. */
export function Disclaimer() {
  return (
    <footer
      role="contentinfo"
      className="fixed inset-x-0 bottom-0 z-20 border-t border-border bg-surface/95 py-1.5 text-center text-xs text-muted"
    >
      {t('app.disclaimer')}
    </footer>
  );
}

export function AppLayout() {
  const { readOnly, unsupported } = useMobileLayout();
  // 계약 .11 F1: 출처 서랍(앱 루트)은 지금 보고 있는 리비전의 출처를 본다
  useProvenanceSnapshot(useSnapshot().snapshotId);
  return (
    <ToastProvider>
      <div className="min-h-screen bg-bg text-fg">
        <a href="#main" className="sr-only focus:not-sr-only">
          {t('app.skipToContent')}
        </a>
        <Header />
        <DegradedBanner />
        <TokenPinnedBanner />
        <ReadOnlyBanner />
        {readOnly ? (
          <p role="note" className="bg-surface px-4 py-1 text-xs text-muted">
            {t('app.mobileReadOnly')}
          </p>
        ) : null}
        {unsupported ? (
          <p role="note" className="bg-surface px-4 py-1 text-xs text-muted">
            {t('app.mobileUnsupported')}
          </p>
        ) : null}
        <main
          id="main"
          className="mx-auto max-w-(--breakpoint-2xl) px-4 pb-16 pt-4"
          data-readonly={readOnly || undefined}
        >
          <Suspense fallback={<p className="text-sm text-muted">{t('app.loading')}</p>}>
            <Outlet />
          </Suspense>
        </main>
        <Disclaimer />
        <TokenDialog />
      </div>
    </ToastProvider>
  );
}
