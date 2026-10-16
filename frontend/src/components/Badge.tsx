import type { ReactNode } from 'react';

/**
 * 배지 톤(D30-3 목업 §4) — 의미는 늘 글자가 나르고(D7), 톤은 눈에 띄는 정도만 바꾼다.
 *  - neutral: 실선 테두리(보류·참고 후보 등)        - muted: 회색 바탕(제외·미확정·미해결·비공식)
 *  - strong: 진한 실선(주의 필요, 예전 톤 — 화면 호환) - dashed: 회색 점선(동률·이전 결과 재사용)
 *  - caution: 주의 점선(순위가 흔들려요·근거와 달라요·추정) - cautionSolid: 주의 실선(낮춤(검증 모순))
 *  - accent: 주색 옅은 바탕(다시 판정 필요)
 */
export type BadgeTone =
  'neutral' | 'muted' | 'strong' | 'dashed' | 'caution' | 'cautionSolid' | 'accent';

export interface BadgeProps {
  children: ReactNode;
  /** 의미는 항상 텍스트로 전달한다(D7). 톤 목록은 BadgeTone */
  tone?: BadgeTone;
  title?: string;
  className?: string;
  /** 좁은 칸에서 줄바꿈 허용(긴 접수 사유가 카드 밖으로 넘치지 않게) */
  wrap?: boolean;
  'data-testid'?: string;
}

export const BADGE_TONES: Record<BadgeTone, string> = {
  neutral: 'border border-border-strong text-fg-2',
  muted: 'border border-transparent bg-chip text-grayed',
  strong: 'border border-fg text-fg font-semibold',
  dashed: 'border border-dashed border-grayed text-fg-2',
  caution: 'border border-dashed border-est-border text-est font-semibold',
  cautionSolid: 'border border-est-border text-est font-semibold',
  accent: 'border border-transparent bg-accent-soft text-accent-ink font-semibold',
};

/** 모든 배지의 바탕. 색이 아니라 텍스트가 의미를 나른다. `data-badge-tone` 은 테스트·리뷰용 */
export function Badge({
  children,
  tone = 'neutral',
  title,
  className = '',
  wrap = false,
  ...rest
}: BadgeProps) {
  return (
    <span
      title={title}
      data-testid={rest['data-testid']}
      data-badge-tone={tone}
      className={`inline-flex max-w-full items-center ${wrap ? 'whitespace-normal' : 'whitespace-nowrap'} rounded-md px-1.5 py-px text-[11px] leading-4 ${BADGE_TONES[tone]} ${className}`}
    >
      {children}
    </span>
  );
}
