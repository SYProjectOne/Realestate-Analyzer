import { useEffect, useMemo, useState } from 'react';
import { useLocation } from 'react-router';
import {
  GLOSSARY_KEYS,
  glossaryItem,
  LABEL_HELP,
  labelText,
  MetaText,
  type GlossaryKey,
} from '@/components';
import { t, type TKey } from '@/i18n';
import { PageShell } from '@/layout/PageShell';

export const CATEGORIES = ['basic', 'who', 'money', 'limits', 'app', 'labels'] as const;
export type Category = (typeof CATEGORIES)[number];

export interface GlossaryEntry {
  /** 카드 id 는 `term-{key}`(다른 화면 '용어 사전에서 보기'가 `#key` 로 연다) */
  key: string;
  /** 용어 이름(검색·팝오버 제목) */
  term: string;
  /** 질문형 카드 제목("전매제한이란?") — ko.json 문구 그대로(조사를 화면에서 만들지 않는다) */
  q: string;
  /** 한 줄 풀이 */
  short: string;
  cat: Category;
}

/**
 * 용어 54개 = ko.json `glossary.items`(48, ko.json 순서) + 라벨 6(`label.help.*` — 출처 범례 '라벨 뜻'과 같은 원본, GL-1).
 * 화면은 서버를 부르지 않는다(#28).
 */
export function glossaryEntries(): GlossaryEntry[] {
  const items: GlossaryEntry[] = GLOSSARY_KEYS.map((k: GlossaryKey) => {
    const item = glossaryItem(k);
    return { key: k, term: item.term, q: item.q, short: item.short, cat: item.cat as Category };
  });
  const labels: GlossaryEntry[] = LABEL_HELP.map((help) => ({
    key: `label_${help.key}`,
    term: labelText(help.label, null, help.human),
    q: t(`glossary.labelQ.${help.key}` as TKey),
    short: t(help.text),
    cat: 'labels',
  }));
  return [...items, ...labels];
}

/** 분류 + 찾는 말(앞뒤 빈칸 뺌)을 함께 거른다(AND, GL-4). 찾는 말은 이름·질문·풀이 어디든 들어 있으면 남는다 */
export function filterGlossary(
  all: readonly GlossaryEntry[],
  cat: Category | null,
  query: string,
): GlossaryEntry[] {
  const q = query.trim();
  return all.filter(
    (e) =>
      (cat === null || e.cat === cat) &&
      (!q || e.term.includes(q) || e.q.includes(q) || e.short.includes(q)),
  );
}

const chipClass = (pressed: boolean) =>
  `min-h-[42px] rounded-full border px-4 py-2 text-[15px] font-medium focus:outline-hidden focus-visible:ring-2 focus-visible:ring-accent ${
    pressed
      ? 'border-fg bg-fg text-bg'
      : 'border-border-strong bg-surface text-fg-2 hover:border-fg-2'
  }`;

/**
 * 용어 사전 `/glossary`(R9-UI P6, 30-proposal §7, 목업 Glossary 보드) — 질문형 카드, 개수 붙은 분류 칩, 분류·찾는 말 함께 거르기.
 * 화면 '?' 의 '용어 사전에서 보기'가 `#key` 로 열면 그 카드로 스크롤(가운데)하고 강조한다. 문구는 ko.json `glossary`·`label.help`.
 * 제도 수치는 넣지 않는다(공고문·청약홈이 기준).
 */
export function GlossaryPage() {
  const [query, setQuery] = useState('');
  const [cat, setCat] = useState<Category | null>(null);
  const { hash } = useLocation();
  const all = useMemo(glossaryEntries, []);
  const shown = filterGlossary(all, cat, query);
  const counts = useMemo(() => {
    const out = new Map<Category, number>();
    for (const e of all) out.set(e.cat, (out.get(e.cat) ?? 0) + 1);
    return out;
  }, [all]);
  // #key 로 열면 그 항목으로 스크롤
  useEffect(() => {
    const id = decodeURIComponent(hash.replace(/^#/, ''));
    if (!id) return;
    document.getElementById(`term-${id}`)?.scrollIntoView?.({ block: 'center' });
  }, [hash]);
  const target = decodeURIComponent(hash.replace(/^#/, ''));
  const q = query.trim();
  const cond = [
    cat !== null
      ? t('glossary.condCategory', { name: t(`glossary.category.${cat}` as TKey) })
      : null,
    q ? t('glossary.condQuery', { q }) : null,
  ].filter((x): x is string => x !== null);

  return (
    <PageShell
      title={t('glossary.heading')}
      intro={<MetaText kind="count" k="glossary.intro" params={{ n: all.length }} />}
    >
      <div className="flex flex-col gap-3 rounded-2xl border border-border bg-surface p-4">
        <label htmlFor="glossary-search" className="text-[13px] text-muted">
          {t('glossary.search')}
        </label>
        <div className="flex min-h-12 items-center gap-2 rounded-xl border border-border-strong bg-surface px-3.5 focus-within:ring-2 focus-within:ring-accent">
          <svg
            aria-hidden
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            className="shrink-0 text-muted"
          >
            <circle cx="11" cy="11" r="7" />
            <path d="m20 20-3.5-3.5" />
          </svg>
          <input
            id="glossary-search"
            type="search"
            value={query}
            placeholder={t('glossary.searchPlaceholder')}
            onChange={(e) => setQuery(e.target.value)}
            className="min-w-0 flex-1 bg-transparent py-2 text-base text-fg outline-hidden placeholder:text-grayed"
          />
        </div>
        <div
          role="group"
          aria-label={t('glossary.categoryGroup')}
          className="flex flex-wrap gap-2"
          data-testid="glossary-categories"
        >
          <button
            type="button"
            aria-pressed={cat === null}
            onClick={() => setCat(null)}
            className={chipClass(cat === null)}
            data-category="all"
          >
            <MetaText
              kind="count"
              k="glossary.chip"
              params={{ name: t('glossary.all'), n: all.length }}
            />
          </button>
          {CATEGORIES.map((c) => (
            <button
              key={c}
              type="button"
              aria-pressed={cat === c}
              onClick={() => setCat(c)}
              className={chipClass(cat === c)}
              data-category={c}
            >
              <MetaText
                kind="count"
                k="glossary.chip"
                params={{ name: t(`glossary.category.${c}` as TKey), n: counts.get(c) ?? 0 }}
              />
            </button>
          ))}
        </div>
        <p className="text-[13px] text-muted">{t('glossary.filterHint')}</p>
      </div>

      <p role="status" className="text-sm text-muted" data-testid="glossary-count">
        {cond.length > 0 ? (
          <MetaText
            kind="count"
            k="glossary.countWith"
            params={{ n: shown.length, cond: cond.join(t('glossary.condJoin')) }}
          />
        ) : (
          <MetaText kind="count" k="glossary.count" params={{ n: shown.length }} />
        )}
      </p>

      {shown.length === 0 ? (
        <p
          role="status"
          className="rounded-[14px] border border-dashed border-border-strong bg-surface p-6 text-center text-[15px] text-fg-2"
        >
          {t('glossary.none')}
        </p>
      ) : null}

      <ul
        aria-label={t('glossary.title')}
        className="grid grid-cols-[repeat(auto-fill,minmax(min(300px,100%),1fr))] gap-3.5"
      >
        {shown.map((e) => {
          const hit = target === e.key;
          return (
            <li key={e.key} className="flex">
              <article
                id={`term-${e.key}`}
                data-term-card={e.key}
                data-target={hit || undefined}
                className={`flex w-full flex-col gap-2 rounded-[14px] p-[18px] ${
                  hit
                    ? 'border-2 border-est-border bg-warn-soft'
                    : 'border border-border bg-surface'
                }`}
              >
                <div className="flex items-baseline justify-between gap-2">
                  <h2 className="text-[17px] font-bold leading-snug text-fg">{e.q}</h2>
                  <span className="shrink-0 rounded-full bg-chip px-2 py-0.5 text-[11px] text-muted">
                    {t(`glossary.category.${e.cat}` as TKey)}
                  </span>
                </div>
                <p className="text-sm leading-relaxed text-fg-2">{e.short}</p>
              </article>
            </li>
          );
        })}
      </ul>

      <p className="rounded-[14px] border border-dashed border-border-strong bg-surface p-[18px] text-sm text-muted">
        {t('glossary.fromOther')}
      </p>
    </PageShell>
  );
}
