import type { HTMLAttributes, ReactNode } from 'react';

export type BannerTone = 'warn' | 'info' | 'note';

export interface BannerProps extends Omit<HTMLAttributes<HTMLDivElement>, 'title' | 'className'> {
  /** warn: 판정기 장애·실패(주의 옅은 바탕) · info: 진행 안내(주색 옅은) · note: 참고(회색 옅은) */
  tone?: BannerTone;
  /** 앞의 굵은 한 문장(없으면 children 만) */
  title?: ReactNode;
  /** 경고 삼각형 아이콘(aria-hidden). 의미는 글자가 나른다 */
  icon?: boolean;
  /** 오른쪽 버튼·링크 */
  actions?: ReactNode;
  children?: ReactNode;
  className?: string;
  'data-testid'?: string;
}

export const BANNER_TONES: Record<BannerTone, string> = {
  warn: 'border-warn-border bg-warn-soft text-warn-ink',
  info: 'border-info-border bg-info-soft text-info-ink',
  note: 'border-border bg-subtle text-fg-2',
};

/** 화면 위 알림 띠(목업 §2) — 둥근 칸 하나. role(alert·status·note)은 쓰는 쪽이 정한다 */
export function Banner({
  tone = 'note',
  title,
  icon = false,
  actions,
  children,
  className = '',
  ...rest
}: BannerProps) {
  return (
    <div
      {...rest}
      data-banner-tone={tone}
      className={`flex flex-wrap items-center gap-x-3 gap-y-2 rounded-xl border px-4 py-3 text-sm ${BANNER_TONES[tone]} ${className}`}
    >
      {icon ? (
        <svg
          aria-hidden
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          className="shrink-0"
        >
          <path d="M12 3 2 21h20z" />
          <path d="M12 10v4" />
          <path d="M12 17h.01" />
        </svg>
      ) : null}
      <span className="min-w-0 flex-[1_1_320px]">
        {title ? <b className="font-semibold">{title}</b> : null}
        {title && children ? ' ' : null}
        {children}
      </span>
      {actions ? <span className="flex flex-wrap items-center gap-2">{actions}</span> : null}
    </div>
  );
}
