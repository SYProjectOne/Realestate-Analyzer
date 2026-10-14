import { useEffect, useId, useRef, useState, type ReactNode } from 'react';
import { Link, useInRouterContext, useLocation } from 'react-router';
import { t } from '@/i18n';
import ko from '@/i18n/ko.json';
import { useIsMobile } from '@/lib/useMediaQuery';

/** 용어 모음 항목 키(ko.json `glossary.items`) — 화면이 쓰는 key 는 타입으로 검사된다 */
export type GlossaryKey = keyof typeof ko.glossary.items;
export const GLOSSARY_KEYS = Object.keys(ko.glossary.items) as GlossaryKey[];

/** 용어 한 개의 표시 이름·한 줄 정의(ko.json 에서만) */
export function glossaryItem(k: GlossaryKey): { term: string; short: string; cat: string } {
  return ko.glossary.items[k];
}

export interface TermProps {
  /** glossary key */
  k: GlossaryKey;
  /** 화면에 보일 용어(열 제목·칸 제목). 없으면 ⓘ 버튼만 */
  children?: ReactNode;
  className?: string;
}

/** 용어 모음 링크(라우터 안에서만 — SPA 이동 + 전역 쿼리 유지). 라우터 밖(차트 갤러리 등)은 링크 없음 */
function MoreLink({ k }: { k: GlossaryKey }) {
  const inRouter = useInRouterContext();
  if (!inRouter) return null;
  return <RouterMoreLink k={k} className="underline" />;
}

function RouterMoreLink({ k, className }: { k: GlossaryKey; className: string }) {
  const { search } = useLocation();
  const params = new URLSearchParams(search);
  const keep = new URLSearchParams();
  for (const key of ['region', 'snapshot', 'scenario']) {
    const v = params.get(key);
    if (v) keep.set(key, v);
  }
  const q = keep.toString();
  return (
    <Link
      to={{ pathname: '/glossary', search: q ? `?${q}` : '', hash: `#${k}` }}
      className={className}
    >
      {t('glossary.more')}
    </Link>
  );
}

/**
 * 용어 ⓘ(R9-UI P6, 30-proposal §7-1) — 열 제목·칸 제목 옆 버튼. 누르면 한 줄 정의 + '용어 모음에서 보기'.
 * aria-expanded·aria-controls, Esc·바깥 클릭으로 닫힌다. 모바일은 아래 시트로 연다. 문구는 ko.json `glossary.items`.
 * 같은 화면에서 같은 용어는 첫 등장에 한 번만 단다(화면 테스트가 data-term 중복을 본다).
 */
export function Term({ k, children, className = '' }: TermProps) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const ref = useRef<HTMLSpanElement>(null);
  const isMobile = useIsMobile();
  const item = glossaryItem(k);
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
    <span ref={ref} className={`relative inline-flex items-center gap-0.5 ${className}`}>
      {children}
      <button
        type="button"
        data-testid="term"
        data-term={k}
        aria-expanded={open}
        aria-controls={id}
        aria-label={t('glossary.open', { term: item.term })}
        onClick={() => setOpen((v) => !v)}
        className="inline-flex h-4 w-4 items-center justify-center rounded-full text-[11px] leading-none text-muted hover:text-fg focus:outline-hidden focus-visible:ring-2 focus-visible:ring-accent"
      >
        <span aria-hidden>ⓘ</span>
      </button>
      {open ? (
        <span
          id={id}
          role="note"
          className={
            isMobile
              ? 'fixed inset-x-0 bottom-0 z-40 flex flex-col gap-1 border-t border-border bg-surface p-4 text-sm font-normal text-fg shadow-lg'
              : 'absolute left-0 top-full z-40 mt-1 flex w-72 flex-col gap-1 rounded-sm border border-border bg-surface p-2 text-left text-xs font-normal normal-case text-fg shadow-lg'
          }
        >
          <span className="font-semibold">{item.term}</span>
          <span className="whitespace-normal">{item.short}</span>
          <span className="flex items-center justify-between gap-2">
            <MoreLink k={k} />
            {isMobile ? (
              <button type="button" onClick={() => setOpen(false)} className="underline">
                {t('glossary.close')}
              </button>
            ) : null}
          </span>
        </span>
      ) : null}
    </span>
  );
}
