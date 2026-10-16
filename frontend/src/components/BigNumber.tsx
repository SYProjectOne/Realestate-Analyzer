import type { ReactNode } from 'react';

export interface BigNumberProps {
  /** 숫자 위 작은 이름("분양가 (84㎡ · 약 34평 기준)") */
  label: ReactNode;
  /** 큰 값 — <FactCell>(사실) 또는 <MetaValue>(개수 등). 이 부품은 숫자를 포맷하지 않는다(FactCell 이 한다) */
  children: ReactNode;
  /** 값 아래 한 줄(확인한 날·계산 기준) */
  caption?: ReactNode;
  /** 글자 크기: md 18px · lg 28px(카드 대표 값) · xl 38px(화면 머리) */
  size?: 'md' | 'lg' | 'xl';
  className?: string;
  'data-testid'?: string;
}

const SIZES: Record<NonNullable<BigNumberProps['size']>, string> = {
  md: 'text-lg',
  lg: 'text-2xl sm:text-[28px]',
  xl: 'text-3xl sm:text-[38px]',
};

/** 크게 보이는 대표 값 하나(목업 Main 카드 "5억 9,850만 ~ 6억 5,090만원 확인됨"). 라벨 배지는 FactCell 이 붙인다 */
export function BigNumber({
  label,
  children,
  caption,
  size = 'lg',
  className = '',
  ...rest
}: BigNumberProps) {
  return (
    <div data-testid={rest['data-testid']} className={`flex flex-col gap-0.5 ${className}`}>
      <span className="text-[13px] text-muted">{label}</span>
      <span
        className={`font-bold leading-tight tracking-tight text-fg tabular-nums ${SIZES[size]}`}
      >
        {children}
      </span>
      {caption ? <span className="text-xs text-muted">{caption}</span> : null}
    </div>
  );
}
