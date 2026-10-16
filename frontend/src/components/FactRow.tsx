import type { ReactNode } from 'react';

export interface FactListProps {
  children: ReactNode;
  /** 줄 사이 구분선 */
  divided?: boolean;
  className?: string;
  'aria-label'?: string;
}

/** FactRow 묶음(`<dl>`). 칸 이름 + 값 줄을 세로로 쌓는다 */
export function FactList({ children, divided = true, className = '', ...rest }: FactListProps) {
  return (
    <dl
      aria-label={rest['aria-label']}
      className={`flex flex-col ${divided ? 'divide-y divide-border' : 'gap-2'} ${className}`}
    >
      {children}
    </dl>
  );
}

export interface FactRowProps {
  /** 칸 이름(ko.json 문구, 필요하면 <Term> 을 함께) */
  label: ReactNode;
  /** 값 — 사실은 <FactCell>(라벨·출처), 사실이 아닌 숫자는 <MetaValue>. 이 부품은 숫자를 직접 만들지 않는다 */
  children: ReactNode;
  /** 값 아래 작은 설명(계산 기준 등) */
  hint?: ReactNode;
  /** stack: 이름 위·값 아래(좁은 카드) · inline: 이름 왼쪽·값 오른쪽(기본) */
  layout?: 'inline' | 'stack';
  className?: string;
  'data-testid'?: string;
}

/** 사실 한 줄: "계약할 때 낼 돈 ··· 3,124만원 추정". FactList(<dl>) 안에 둔다 */
export function FactRow({
  label,
  children,
  hint,
  layout = 'inline',
  className = '',
  ...rest
}: FactRowProps) {
  return (
    <div
      data-testid={rest['data-testid']}
      className={`flex py-2 first:pt-0 last:pb-0 ${
        layout === 'stack'
          ? 'flex-col gap-1'
          : 'flex-wrap items-baseline justify-between gap-x-4 gap-y-1'
      } ${className}`}
    >
      <dt className="text-[13px] text-muted">{label}</dt>
      <dd className={`flex flex-col gap-0.5 ${layout === 'stack' ? '' : 'items-end text-right'}`}>
        <span className="text-[15px] font-semibold text-fg">{children}</span>
        {hint ? <span className="text-xs text-muted">{hint}</span> : null}
      </dd>
    </div>
  );
}
