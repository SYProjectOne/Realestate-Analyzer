import type { ReactNode } from 'react';
import { Card } from '@/components';

/**
 * R11(D30) 목업 구역 카드: 작은 머리말(kicker) + 질문형 h2 + "이게 뭐예요?" 줄(선택) + 한 줄 안내(선택).
 * 구역 이름(`name` — 메뉴·표에 쓰는 공식 이름)은 `aria-label` 로 남기고, 보이는 제목은 질문 문장이다.
 * 그래서 구역(region)·표 이름으로 찾는 기존 테스트와 출처 링크가 그대로 산다. 문구는 모두 호출 쪽 ko.json 키.
 */
export function QuestionSection({
  name,
  title,
  kicker,
  whatLabel,
  what,
  hint,
  actions,
  id,
  className = '',
  children,
  'data-testid': testId,
}: {
  /** 구역 공식 이름(aria-label) */
  name: string;
  /** 보이는 질문형 제목(h2) */
  title: string;
  /** 제목 위 작은 머리말(예: "① 일정·체크리스트", "편집하는 사람용") */
  kicker?: ReactNode;
  /** "이게 뭐예요?" 같은 설명 앞 꼬리표 */
  whatLabel?: string;
  /** 설명 한 줄(whatLabel 뒤) */
  what?: ReactNode;
  /** 제목 아래 안내 */
  hint?: ReactNode;
  /** 제목 오른쪽(건수 알약·버튼) */
  actions?: ReactNode;
  id?: string;
  className?: string;
  children?: ReactNode;
  'data-testid'?: string;
}) {
  return (
    <Card
      as="section"
      id={id}
      aria-label={name}
      padding="md"
      data-testid={testId}
      className={`flex min-w-0 scroll-mt-24 flex-col gap-4 ${className}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <div className="flex min-w-0 flex-1 basis-80 flex-col gap-1.5">
          {kicker ? <p className="text-[13px] font-semibold text-accent-ink">{kicker}</p> : null}
          <h2 className="text-lg font-bold leading-snug text-fg sm:text-[22px]">{title}</h2>
          {what ? (
            <p className="text-sm leading-relaxed text-fg-2">
              {whatLabel ? (
                <b className="mr-1.5 inline-flex rounded-md bg-accent-soft px-1.5 py-px text-xs font-semibold text-accent-ink">
                  {whatLabel}
                </b>
              ) : null}
              {what}
            </p>
          ) : null}
          {hint ? <p className="text-sm leading-relaxed text-muted">{hint}</p> : null}
        </div>
        {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
      </div>
      {children}
    </Card>
  );
}

/**
 * 차트 틀(ChartFrame)을 구역 카드 안에 넣을 때 바깥 테두리·여백을 지운다(카드 안 카드가 되지 않게).
 * 차트 부품은 R11-CHARTS 소유라 여기서 감싸기만 한다.
 */
export const FLAT_CHART =
  '[&>figure]:rounded-none [&>figure]:border-0 [&>figure]:bg-transparent [&>figure]:p-0';
