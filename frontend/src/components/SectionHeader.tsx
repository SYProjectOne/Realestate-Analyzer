import type { ReactNode } from 'react';

export interface SectionHeaderProps {
  /** 질문형 제목(목업: "일정은 어디쯤 왔나요?") — ko.json 문구 */
  title: string;
  /** 제목 아래 한 줄 안내(무엇을 보는 칸인지) */
  hint?: ReactNode;
  /** 제목 단계(기본 h2) */
  level?: 2 | 3;
  /** 제목 id — 구역 `aria-labelledby` 에 쓴다 */
  id?: string;
  /** 제목 오른쪽 도구(버튼·링크) */
  actions?: ReactNode;
  className?: string;
}

/** 구역 머리: 질문형 h2(22px 굵게) + 한 줄 안내(14px 설명색). 화면마다 같은 모양 */
export function SectionHeader({
  title,
  hint,
  level = 2,
  id,
  actions,
  className = '',
}: SectionHeaderProps) {
  const Heading = level === 2 ? 'h2' : 'h3';
  return (
    <div className={`flex flex-wrap items-start justify-between gap-x-4 gap-y-2 ${className}`}>
      <div className="flex min-w-0 flex-col gap-1">
        <Heading
          id={id}
          className={
            level === 2
              ? 'text-lg font-bold leading-snug text-fg sm:text-[22px]'
              : 'text-base font-bold leading-snug text-fg sm:text-[17px]'
          }
        >
          {title}
        </Heading>
        {hint ? <p className="text-sm text-muted">{hint}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}
