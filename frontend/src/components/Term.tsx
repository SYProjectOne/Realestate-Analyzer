import { useEffect, useId, useRef, useState, type ReactNode } from 'react';
import { Link, useInRouterContext, useLocation } from 'react-router';
import glossaryKeys from 'virtual:ko/keys/glossary.items';
import { t, type TKey } from '@/i18n';
import type ko from '@/i18n/ko.json';
import { useIsMobile } from '@/lib/useMediaQuery';

/** 용어 모음 항목 키(ko.json `glossary.items`) — 화면이 쓰는 key 는 타입으로 검사된다 */
export type GlossaryKey = keyof typeof ko.glossary.items;
/** 키 이름만(ko.json 순서). 본문은 `glossary` 이름공간 — R11-I18N, 라우트가 화면 청크와 함께 받는다 */
export const GLOSSARY_KEYS = glossaryKeys as GlossaryKey[];

/** 용어 한 개의 표시 이름·질문형 제목(q, 용어 사전 카드)·한 줄 정의(ko.json 에서만) */
export function glossaryItem(k: GlossaryKey): {
  term: string;
  q: string;
  short: string;
  cat: string;
} {
  const field = (f: 'term' | 'q' | 'short' | 'cat') => t(`glossary.items.${k}.${f}` as TKey);
  return { term: field('term'), q: field('q'), short: field('short'), cat: field('cat') };
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
  return <RouterMoreLink k={k} className="self-start text-accent hover:underline" />;
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
 * 용어 '?'(R9-UI P6, 30-proposal §7-1 · 목업 Shell §3) — 열 제목·칸 제목 옆 버튼. 누르면 한 줄 정의 + '용어 사전에서 보기'.
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
    <span ref={ref} className={`relative inline-flex items-center gap-1 ${className}`}>
      {children}
      <button
        type="button"
        data-testid="term"
        data-term={k}
        aria-expanded={open}
        aria-controls={id}
        aria-label={t('glossary.open', { term: item.term })}
        onClick={() => setOpen((v) => !v)}
        // 목업 §3: 동그란 '?' 버튼(20px, 누르는 칸은 24px)
        className="-my-1 inline-flex size-6 shrink-0 items-center justify-center rounded-full focus:outline-hidden focus-visible:ring-2 focus-visible:ring-accent"
      >
        <span
          aria-hidden
          className="inline-flex size-5 items-center justify-center rounded-full border border-grayed bg-surface text-xs font-bold leading-none text-fg-2 hover:border-fg-2 hover:text-fg"
        >
          ?
        </span>
      </button>
      {open && isMobile ? (
        // 휴대폰(SH-19): 아래에서 올라오는 판 + 뒤 화면 어둡게 + 닫기
        <span
          aria-hidden
          onClick={() => setOpen(false)}
          className="fixed inset-0 z-40 bg-overlay/45"
        />
      ) : null}
      {open ? (
        <span
          id={id}
          role="note"
          data-term-sheet={isMobile ? 'bottom' : 'popover'}
          className={
            isMobile
              ? 'fixed inset-x-0 bottom-0 z-50 flex flex-col gap-2 rounded-t-[18px] bg-surface px-[18px] pb-5 pt-4 text-left text-sm font-normal normal-case text-fg shadow-2xl'
              : 'absolute left-0 top-full z-40 mt-1.5 flex w-72 flex-col gap-1.5 rounded-xl border border-info-border bg-surface p-3.5 text-left text-sm font-normal normal-case text-fg shadow-lg'
          }
        >
          {isMobile ? (
            <span aria-hidden className="h-1 w-10 self-center rounded-full bg-border-strong" />
          ) : null}
          <span className={isMobile ? 'text-base font-bold' : 'text-[15px] font-bold'}>
            {item.term}
          </span>
          <span className="whitespace-normal text-fg-2">{item.short}</span>
          <span className="flex flex-col gap-2 text-[13px]">
            <MoreLink k={k} />
            {isMobile ? (
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="min-h-11 rounded-[10px] border border-border-strong bg-surface px-3.5 text-sm font-semibold text-fg"
              >
                {t('glossary.close')}
              </button>
            ) : null}
          </span>
        </span>
      ) : null}
    </span>
  );
}
