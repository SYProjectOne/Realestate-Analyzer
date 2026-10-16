import type { ReactNode } from 'react';

/**
 * 상태 알약 톤(목업 §4 접수 상태 · Main 카드):
 *  - accent: 주색 바탕(접수 가능처럼 지금 할 수 있는 것) · outline: 테두리만(일정 미정 등)
 *  - muted: 회색 바탕(확인 못 함·미정) · strike: 회색 바탕 + 취소선(접수 불가) · neutral: 칩 바탕(공급 종류 등)
 *  - warn: 주의 옅은 바탕
 * 의미는 늘 글자로(D7) — 톤은 눈에 띄는 정도만.
 */
export type StatusPillTone = 'accent' | 'outline' | 'muted' | 'strike' | 'neutral' | 'warn';

export interface StatusPillProps {
  children: ReactNode;
  tone?: StatusPillTone;
  /** 글자 앞 작은 점(accent 톤의 '지금 가능' 표시) */
  dot?: boolean;
  /** 크기: sm(표·칩 줄) · md(카드 머리) */
  size?: 'sm' | 'md';
  title?: string;
  /** 좁은 칸에서 줄바꿈 허용 */
  wrap?: boolean;
  className?: string;
  'data-testid'?: string;
}

export const PILL_TONES: Record<StatusPillTone, string> = {
  accent: 'bg-accent text-accent-fg border-transparent',
  outline: 'border-border-strong text-fg-2',
  muted: 'bg-chip text-muted border-transparent',
  strike: 'bg-chip text-fg-2 border-transparent line-through',
  neutral: 'bg-chip text-fg-2 border-transparent',
  warn: 'bg-warn-soft text-warn-ink border-warn-border',
};

/** 둥근 상태 알약 — 접수 상태·공급 종류·점수 상태 같은 짧은 상태. `data-pill-tone` 은 테스트·리뷰용 */
export function StatusPill({
  children,
  tone = 'neutral',
  dot = false,
  size = 'sm',
  title,
  wrap = false,
  className = '',
  ...rest
}: StatusPillProps) {
  const sz = size === 'md' ? 'px-2.5 py-1 text-[13px]' : 'px-2 py-0.5 text-xs';
  return (
    <span
      title={title}
      data-testid={rest['data-testid']}
      data-pill-tone={tone}
      className={`inline-flex max-w-full items-center gap-1.5 rounded-full border font-semibold leading-4 ${wrap ? 'whitespace-normal' : 'whitespace-nowrap'} ${sz} ${PILL_TONES[tone]} ${className}`}
    >
      {dot ? <span aria-hidden className="size-1.5 shrink-0 rounded-full bg-current" /> : null}
      {children}
    </span>
  );
}
