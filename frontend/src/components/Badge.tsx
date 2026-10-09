import type { ReactNode } from 'react';

export interface BadgeProps {
  children: ReactNode;
  /** muted = 회색(미확정·미해결·비공식), strong = 강조(주의 필요). 의미는 항상 텍스트로 전달한다(D7). */
  tone?: 'neutral' | 'muted' | 'strong';
  title?: string;
  className?: string;
  'data-testid'?: string;
}

const TONES: Record<NonNullable<BadgeProps['tone']>, string> = {
  neutral: 'border-border text-fg',
  muted: 'border-border text-grayed',
  strong: 'border-fg text-fg font-semibold',
};

/** 모든 배지의 바탕. 색이 아니라 텍스트가 의미를 나른다. */
export function Badge({ children, tone = 'neutral', title, className = '', ...rest }: BadgeProps) {
  return (
    <span
      title={title}
      data-testid={rest['data-testid']}
      className={`inline-flex items-center whitespace-nowrap rounded-sm border px-1.5 py-px text-[11px] leading-4 ${TONES[tone]} ${className}`}
    >
      {children}
    </span>
  );
}
