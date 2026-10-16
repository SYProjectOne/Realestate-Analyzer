import type { HTMLAttributes, ReactNode } from 'react';

export type CardTone = 'default' | 'subtle' | 'accent' | 'warn' | 'info';
export type CardPadding = 'none' | 'sm' | 'md' | 'lg';

export interface CardProps extends Omit<HTMLAttributes<HTMLElement>, 'className' | 'children'> {
  children: ReactNode;
  /** 바탕: default 흰 카드 · subtle 옅은 회색 칸 · accent 주색 옅은 · warn 주의 옅은 · info 안내 옅은 */
  tone?: CardTone;
  /** 안쪽 여백: none 0 · sm 12px · md 18px · lg 24px(모바일은 한 단계 작게) */
  padding?: CardPadding;
  /** 그릴 요소(기본 div). 목록 안 카드면 li, 구역이면 section(aria-label 을 넘긴다) */
  as?: 'div' | 'section' | 'article' | 'li' | 'aside';
  /** 누르는 카드(링크를 감싼 카드) — 마우스를 올리면 테두리가 짙어진다 */
  interactive?: boolean;
  className?: string;
}

export const CARD_TONES: Record<CardTone, string> = {
  default: 'bg-surface border-border',
  subtle: 'bg-subtle border-border',
  accent: 'bg-accent-soft border-transparent',
  warn: 'bg-warn-soft border-warn-border',
  info: 'bg-info-soft border-info-border',
};

const PADDING: Record<CardPadding, string> = {
  none: '',
  sm: 'p-3',
  md: 'p-4 sm:p-[18px]',
  lg: 'p-4 sm:p-6',
};

/** 목업 카드(.card: 흰 바탕 · 1px #E3E7EC · 둥근 16px). 화면 구역·요약 칸·목록 카드의 바탕 */
export function Card({
  children,
  tone = 'default',
  padding = 'md',
  as: Tag = 'div',
  interactive = false,
  className = '',
  ...rest
}: CardProps) {
  return (
    <Tag
      {...rest}
      data-card-tone={tone}
      className={`rounded-2xl border ${CARD_TONES[tone]} ${PADDING[padding]} ${
        interactive ? 'transition-colors hover:border-border-strong focus-within:border-accent' : ''
      } ${className}`}
    >
      {children}
    </Tag>
  );
}
