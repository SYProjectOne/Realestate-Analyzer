import type { ReactNode } from 'react';

export interface PageShellProps {
  /** h1 제목 (ko.json `page.<id>.title`) */
  title: string;
  /** 제목 오른쪽 도구(버튼·필터 요약 등) */
  actions?: ReactNode;
  children?: ReactNode;
}

/** 모든 화면의 골격: h1 + 본문. 화면 id는 라우트 handle이 갖는다. */
export function PageShell({ title, actions, children }: PageShellProps) {
  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">{title}</h1>
        {actions}
      </div>
      {children}
    </section>
  );
}
