import { useEffect, useMemo, useState } from 'react';
import { useLocation } from 'react-router';
import { GLOSSARY_KEYS, glossaryItem, type GlossaryKey } from '@/components';
import { t, type TKey } from '@/i18n';
import { PageShell } from '@/layout/PageShell';

const CATEGORIES = ['basic', 'who', 'money', 'limits', 'app', 'labels'] as const;
type Category = (typeof CATEGORIES)[number];

/** 라벨 분류는 라벨 뜻(P3 범례 label.help)을 그대로 보인다 — 같은 원본 */
const LABEL_HELP: readonly { key: string; text: TKey }[] = [
  { key: 'label_confirmed', text: 'label.help.confirmed' },
  { key: 'label_estimated', text: 'label.help.estimated' },
  { key: 'label_unofficial', text: 'label.help.unofficial' },
  { key: 'label_reprocessed', text: 'label.help.reprocessed' },
  { key: 'label_unknown', text: 'label.help.unknown' },
  { key: 'label_human', text: 'label.help.human' },
];

interface Entry {
  key: string;
  term: string;
  short: string;
  cat: Category;
}

function entries(): Entry[] {
  const items: Entry[] = GLOSSARY_KEYS.map((k: GlossaryKey) => {
    const item = glossaryItem(k);
    return { key: k, term: item.term, short: item.short, cat: item.cat as Category };
  });
  const labels: Entry[] = LABEL_HELP.map(({ key, text }) => {
    const full = t(text);
    const term = full.split(' — ')[0] ?? full;
    return { key, term, short: full, cat: 'labels' };
  });
  return [...items, ...labels];
}

/**
 * 용어 모음 `/glossary`(R9-UI P6, 30-proposal §7) — 분류 버튼 + 검색 + 한 줄 정의. 화면 ⓘ 의 '용어 모음에서 보기'가 `#key` 로 연다.
 * 문구는 ko.json `glossary`. 제도 수치는 넣지 않는다(공고문·청약홈이 기준).
 */
export function GlossaryPage() {
  const [query, setQuery] = useState('');
  const [cat, setCat] = useState<Category | null>(null);
  const { hash } = useLocation();
  const all = useMemo(entries, []);
  const q = query.trim();
  const shown = all.filter(
    (e) => (cat === null || e.cat === cat) && (!q || e.term.includes(q) || e.short.includes(q)),
  );
  // #key 로 열면 그 항목으로 스크롤
  useEffect(() => {
    const id = decodeURIComponent(hash.replace(/^#/, ''));
    if (!id) return;
    document.getElementById(`term-${id}`)?.scrollIntoView?.({ block: 'center' });
  }, [hash]);
  const target = decodeURIComponent(hash.replace(/^#/, ''));
  return (
    <PageShell title={t('glossary.title')} intro={t('glossary.intro')}>
      <div className="flex flex-col gap-3">
        <label className="flex flex-col gap-0.5 text-xs">
          <span className="text-muted">{t('glossary.search')}</span>
          <input
            type="search"
            value={query}
            placeholder={t('glossary.searchPlaceholder')}
            onChange={(e) => setQuery(e.target.value)}
            className="w-64 max-w-full rounded-sm border border-border bg-surface px-2 py-1 text-sm text-fg"
          />
        </label>
        <div role="group" aria-label={t('glossary.title')} className="flex flex-wrap gap-1">
          <button
            type="button"
            aria-pressed={cat === null}
            onClick={() => setCat(null)}
            className={`rounded-sm border border-border px-2 py-0.5 text-sm ${cat === null ? 'bg-accent text-accent-fg' : ''}`}
          >
            {t('glossary.all')}
          </button>
          {CATEGORIES.map((c) => (
            <button
              key={c}
              type="button"
              aria-pressed={cat === c}
              onClick={() => setCat(c)}
              className={`rounded-sm border border-border px-2 py-0.5 text-sm ${cat === c ? 'bg-accent text-accent-fg' : ''}`}
            >
              {t(`glossary.category.${c}` as TKey)}
            </button>
          ))}
        </div>
        {shown.length === 0 ? (
          <p role="status" className="text-sm text-muted">
            {t('glossary.none')}
          </p>
        ) : null}
        <ul aria-label={t('glossary.title')} className="flex flex-col divide-y divide-border">
          {shown.map((e) => (
            <li
              key={e.key}
              id={`term-${e.key}`}
              className={`flex flex-col gap-0.5 py-2 ${target === e.key ? 'rounded-sm bg-surface px-2' : ''}`}
            >
              <span className="flex flex-wrap items-center gap-2">
                <span className="font-semibold">{e.term}</span>
                <span className="text-xs text-muted">
                  {t(`glossary.category.${e.cat}` as TKey)}
                </span>
              </span>
              <span className="text-sm">{e.short}</span>
            </li>
          ))}
        </ul>
      </div>
    </PageShell>
  );
}
