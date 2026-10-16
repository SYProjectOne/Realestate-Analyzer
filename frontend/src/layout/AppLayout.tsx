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
import { MOBILE_QUERY } from '@/lib/useMediaQuery';
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

/** 휴대폰에서 글꼴 조각 내려받기를 미루는 시간(ms) — 첫 화면 자료(API·화면 청크)와 대역을 다투지 않게 */
export const MOBILE_FONT_DELAY_MS = 4000;

/**
 * 글꼴 불러오기 시점. 데스크톱은 첫 렌더 직후, 휴대폰(≤768px, 느린 망)은 페이지 load 뒤 MOBILE_FONT_DELAY_MS 가 지나
 * 브라우저가 한가할 때 — 한글 글꼴 조각(굵기 4종 × 수십 개)이 첫 화면 자료와 대역을 다투면 휴대폰 LCP 가 두 배가 됐다
 * (Lighthouse 모바일 / 3.1초 → 6.3초). 그 전에는 시스템 한글 글꼴로 보인다(font-display: swap).
 */
function loadFontsWhenIdle(): () => void {
  const load = () => void import('./fonts');
  const mobile = window.matchMedia?.(MOBILE_QUERY).matches ?? false;
  if (!mobile) {
    load();
    return () => {};
  }
  let timer: number | undefined;
  const schedule = () => {
    timer = window.setTimeout(() => {
      if ('requestIdleCallback' in window) window.requestIdleCallback(load, { timeout: 2000 });
      else load();
    }, MOBILE_FONT_DELAY_MS);
  };
  if (document.readyState === 'complete') schedule();
  else window.addEventListener('load', schedule, { once: true });
  return () => {
    window.removeEventListener('load', schedule);
    if (timer !== undefined) window.clearTimeout(timer);
  };
}

export function AppLayout() {
  const { isMobile, readOnly, unsupported } = useMobileLayout();
  // 계약 .11 F1: 출처 서랍(앱 루트)은 지금 보고 있는 리비전의 출처를 본다
  useProvenanceSnapshot(useSnapshot().snapshotId);
  // D30-3: 글꼴 @font-face(약 230kB)는 첫 렌더 뒤 따로 붙인다(첫 화면을 막지 않게, layout/fonts.ts)
  useEffect(() => loadFontsWhenIdle(), []);
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
          className="mx-auto flex max-w-(--breakpoint-2xl) flex-col gap-2 px-4 pt-4 empty:hidden sm:px-6"
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
          className="mx-auto max-w-(--breakpoint-2xl) px-4 pb-20 pt-4 sm:px-6 mobile:pb-36"
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
