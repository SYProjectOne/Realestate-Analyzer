import { Suspense, useEffect } from 'react';
import { Outlet } from 'react-router';
import { BackfilledBanner } from '@/app/BackfilledBanner';
import { DegradedBanner } from '@/app/DegradedBanner';
import { RegionLoadingBanner } from '@/app/RegionLoadingBanner';
import { ReadOnlyBanner, TokenDialog, TokenPinnedBanner } from '@/app/TokenDialog';
import { ToastProvider } from '@/app/toast';
import { Skeleton } from '@/components/Skeleton';
import { useProvenanceSnapshot } from '@/components/provenanceContext';
import { useMobileLayout } from '@/hooks/useMobileLayout';
import { useSnapshot } from '@/hooks/useSnapshot';
import { t } from '@/i18n';
import { BottomNav } from './BottomNav';
import { Header } from './Header';

/** 하단 고정 문구 — D7 "모든 판정 화면 하단에 투자 권유 아님 · 상대 비교". 전 화면에 둔다(휴대폰은 하단 메뉴 바로 위). */
export function Disclaimer() {
  return (
    <footer
      role="contentinfo"
      className="fixed inset-x-0 bottom-0 z-20 border-t border-border bg-surface/95 py-1.5 text-center text-xs text-muted backdrop-blur-sm mobile:bottom-[calc(3.5rem+env(safe-area-inset-bottom))]"
    >
      {t('app.disclaimer')}
    </footer>
  );
}

/** 휴대폰 정책 칩(목업 §2 맨 아래 회색 칩): 보기만 / 컴퓨터에서 */
function MobileNote({ text }: { text: string }) {
  return (
    <p
      role="note"
      className="self-start rounded-[10px] border border-border bg-surface px-3 py-2 text-[13px] text-fg-2"
    >
      {text}
    </p>
  );
}

export function AppLayout() {
  const { isMobile, readOnly, unsupported } = useMobileLayout();
  // 계약 .11 F1: 출처 서랍(앱 루트)은 지금 보고 있는 리비전의 출처를 본다
  useProvenanceSnapshot(useSnapshot().snapshotId);
  // D30-3: 글꼴 @font-face(약 230kB)는 첫 렌더 뒤 따로 붙인다(첫 화면을 막지 않게, layout/fonts.ts)
  useEffect(() => {
    void import('./fonts');
  }, []);
  return (
    <ToastProvider>
      <div className="min-h-screen bg-bg font-sans text-fg">
        <a
          href="#main"
          className="sr-only rounded-lg bg-toast px-3 py-2 text-[13px] text-toast-fg focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-50"
        >
          {t('app.skipToContent')}
        </a>
        <Header />
        {/* 알림 띠(목업 §2) — 순서: 판정기 장애 → 지역 처음 분석 → 다시 계산한 값 → 탭 고정 → 읽기 전용(#8) → 휴대폰 칩 */}
        <div
          data-testid="banner-stack"
          className="mx-auto flex max-w-[1280px] flex-col gap-2 px-4 pt-4 empty:hidden sm:px-6"
        >
          <DegradedBanner />
          <RegionLoadingBanner />
          <BackfilledBanner />
          <TokenPinnedBanner />
          <ReadOnlyBanner />
          {readOnly ? <MobileNote text={t('app.mobileReadOnly')} /> : null}
          {unsupported ? <MobileNote text={t('app.mobileUnsupported')} /> : null}
        </div>
        <main
          id="main"
          className="mx-auto max-w-[1280px] px-4 pb-20 pt-5 sm:px-6 sm:pt-7 mobile:pb-36"
          data-readonly={readOnly || undefined}
        >
          <Suspense fallback={<Skeleton />}>
            <Outlet />
          </Suspense>
        </main>
        <Disclaimer />
        {isMobile ? <BottomNav /> : null}
        <TokenDialog />
      </div>
    </ToastProvider>
  );
}
