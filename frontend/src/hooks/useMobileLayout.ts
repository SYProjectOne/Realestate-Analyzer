import { useMatches } from 'react-router';
import { useIsMobile } from '@/lib/useMediaQuery';

/** 라우트 handle에 적는 모바일 정책. D7: 모바일(≤768px)은 G1·G2·G3만 읽기 전용으로 지원. */
export type MobilePolicy = 'readonly' | 'unsupported';

export interface RouteHandle {
  /** 화면 id (G0, G0-2, G1 …) */
  screen: string;
  mobile: MobilePolicy;
}

export interface MobileLayout {
  isMobile: boolean;
  /** 모바일이고 이 화면이 읽기 전용 지원 화면 → 편집·실행 UI(폼·버튼·체크)를 숨긴다 */
  readOnly: boolean;
  /** 모바일인데 지원하지 않는 화면 → 레이아웃이 안내를 띄운다 */
  unsupported: boolean;
}

/** 모바일 읽기 전용 레이아웃 훅. 화면은 `readOnly`가 true면 쓰기 UI를 렌더하지 않는다. */
export function useMobileLayout(): MobileLayout {
  const isMobile = useIsMobile();
  const matches = useMatches();
  const handle = [...matches].reverse().find((m) => (m.handle as RouteHandle | undefined)?.mobile)
    ?.handle as RouteHandle | undefined;
  const policy: MobilePolicy = handle?.mobile ?? 'unsupported';
  return {
    isMobile,
    readOnly: isMobile && policy === 'readonly',
    unsupported: isMobile && policy === 'unsupported',
  };
}
