import { useEffect, useId, useRef, useState, type ReactNode } from 'react';

/**
 * 화면 안 짧은 설명 '?' 버튼(목업 `.q` — 22px 동그라미). 용어 사전(`Term`)에 없는 화면 고유 설명(법정동·행정동,
 * 기준일·수정본, 지역 범위 확장)에 쓴다. 누르면 바로 아래(같은 줄 끝)에 설명 칸을 펼친다 — aria-expanded·aria-controls,
 * Esc·바깥 클릭으로 닫힌다. 문구는 호출 측이 ko.json 에서 넘긴다. R11-SETUP(G0·G0-2·G8) 공용.
 */
export function HelpToggle({
  label,
  children,
  align = 'left',
  className = '',
}: {
  /** 버튼 이름(aria-label) */
  label: string;
  /** 펼친 설명 */
  children: ReactNode;
  /** 설명 칸을 버튼 왼쪽 끝(left) 또는 오른쪽 끝(right)에 맞춘다 */
  align?: 'left' | 'right';
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    const onDown = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('keydown', onKey);
    document.addEventListener('mousedown', onDown);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('mousedown', onDown);
    };
  }, [open]);
  return (
    <span ref={ref} className={`relative inline-flex items-center ${className}`}>
      <button
        type="button"
        aria-label={label}
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((v) => !v)}
        className="inline-flex size-[22px] shrink-0 items-center justify-center rounded-full border border-grayed bg-surface text-xs font-bold leading-none text-muted hover:border-accent hover:text-accent focus:outline-hidden focus-visible:ring-2 focus-visible:ring-accent"
      >
        <span aria-hidden>?</span>
      </button>
      {open ? (
        <span
          id={id}
          role="note"
          data-testid="help-note"
          className={`absolute ${align === 'right' ? 'right-0' : 'left-0'} top-full z-40 mt-1.5 w-72 max-w-[80vw] rounded-xl border border-info-border bg-surface p-3.5 text-left text-sm font-normal leading-relaxed text-fg-2 shadow-lg`}
        >
          {children}
        </span>
      ) : null}
    </span>
  );
}
