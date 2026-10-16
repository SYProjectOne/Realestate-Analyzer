import type { ReactNode } from 'react';
import { Term, type GlossaryKey } from './Term';

export interface KeepNoteProps {
  /** 조건 이름("되팔기 (전매)") — ko.json 문구 */
  label: string;
  /** 이름 옆 '?' 용어 풀이(glossary key) */
  term?: GlossaryKey;
  /** 큰 글씨 값 — 사실은 <FactCell>, 문구는 서버 값·ko.json. 이 부품은 값을 만들지 않는다 */
  value: ReactNode;
  /** 값 아래 작은 줄(남은 날·근거 값 + 라벨) */
  detail?: ReactNode;
  /** warn: 지금 걸려 있는 제한처럼 눈여겨볼 칸(주의 옅은 바탕) · neutral: 보통 */
  tone?: 'neutral' | 'warn';
  className?: string;
  'data-testid'?: string;
}

/**
 * "꼭 확인할 조건" 칸(목업 Detail §조건): 이름 + '?' · 큰 값 · 작은 근거 줄. 강조(warn)는 화면이 서버 값으로 정한
 * 경우에만(예: 제한이 아직 남음) — 이 부품이 판단하지 않는다. 의미는 글자로(D7).
 */
export function KeepNote({
  label,
  term,
  value,
  detail,
  tone = 'neutral',
  className = '',
  ...rest
}: KeepNoteProps) {
  return (
    <div
      data-testid={rest['data-testid']}
      data-note-tone={tone}
      className={`flex flex-col gap-2 rounded-[14px] border p-4 ${
        tone === 'warn' ? 'border-warn-border bg-warn-soft' : 'border-border bg-subtle'
      } ${className}`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className={`text-[13px] ${tone === 'warn' ? 'text-warn-ink' : 'text-muted'}`}>
          {label}
        </span>
        {term ? <Term k={term} /> : null}
      </div>
      <span className="text-lg font-bold leading-snug text-fg">{value}</span>
      {detail ? (
        <span className={`text-xs ${tone === 'warn' ? 'text-warn-ink' : 'text-muted'}`}>
          {detail}
        </span>
      ) : null}
    </div>
  );
}
