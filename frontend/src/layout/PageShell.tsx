import type { ReactNode } from 'react';
import { ProvenanceLegend } from '@/components/ProvenanceLegend';

export interface PageShellProps {
  /** h1 제목 (ko.json `page.<id>.title`) */
  title: string;
  /** 제목 오른쪽 도구(버튼·필터 요약 등) */
  actions?: ReactNode;
  /** 제목 아래 한 줄 안내(화면이 무엇인지) */
  intro?: ReactNode;
  /** 출처 범례 한 줄(P3: "밑줄 친 숫자를 누르면 출처·확인일이 열립니다 · 라벨 뜻 ⓘ") — 숫자를 보이는 화면 */
  legend?: boolean;
  children?: ReactNode;
}

/** 모든 화면의 골격(목업 각 보드 머리): h1(30px 굵게) + 한 줄 안내 + 본문. 화면 id는 라우트 handle이 갖는다. */
export function PageShell({ title, actions, intro, legend = false, children }: PageShellProps) {
  return (
    <section className="flex flex-col gap-6">
      <div className="flex flex-col gap-1.5">
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
          <h1 className="text-2xl font-bold leading-tight tracking-tight text-fg sm:text-[30px]">
            {title}
          </h1>
          {actions}
        </div>
        {intro ? <p className="text-[15px] leading-relaxed text-muted">{intro}</p> : null}
        {legend ? <ProvenanceLegend className="mt-1" /> : null}
      </div>
      {children}
    </section>
  );
}
