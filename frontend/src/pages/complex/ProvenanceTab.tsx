import { useMemo, useState } from 'react';
import { rawDocumentUrl, useProvenance, useRawText } from '@/api/hooks';
import type { ComplexDetail, Fact } from '@/api/types';
import { EmptyState, FactCell, LabelBadge } from '@/components';
import { t, tDynamic } from '@/i18n';
import { formatDate } from '@/lib/format';
import { unitOf } from '../_shared';

interface ProvItem {
  key: string;
  title: string;
  fact: Fact;
}

/** 헤더·가격 Fact 중 출처(prov)가 있는 것 — 원문 하이라이트 대상 목록 */
function collect(detail: ComplexDetail): ProvItem[] {
  const out: ProvItem[] = [];
  const add = (key: string, title: string, fact: Fact | null | undefined) => {
    if (fact?.prov) out.push({ key, title, fact });
  };
  add('price_low', t('page.G2.col.price'), detail.price.price_low);
  add('price_high', t('page.G2.col.price'), detail.price.price_high);
  const header = detail.header as unknown as Record<string, Fact | null | undefined>;
  for (const field of [
    'units_total',
    'notice_date',
    'winner_date',
    'move_in_ym',
    'resale_months',
    'resale_end',
    'residency_months',
    'rewin_restriction_years',
    'land_type',
    'price_cap',
    'regulated',
    'housing_type',
  ]) {
    add(field, tDynamic(`page.G3.headerFields.${field}`, field), header[field]);
  }
  for (const type of detail.types) {
    add(
      `type_${type.type_code}`,
      `${t('page.G3.price.max')} ${type.type_code}`,
      type.max_price_won,
    );
  }
  return out;
}

export interface HighlightParts {
  before: string;
  mark: string;
  after: string;
  /** 오프셋이 맞지 않아 문자열 검색으로 찾았는지 */
  searched: boolean;
}

/** 원문 텍스트에서 발췌 위치를 찾는다: excerpt_start/end가 맞으면 그대로, 아니면 문자열 검색 */
export function highlightExcerpt(
  text: string,
  excerpt: string | null | undefined,
  start: number | null | undefined,
  end: number | null | undefined,
): HighlightParts | null {
  if (!excerpt) return null;
  if (
    typeof start === 'number' &&
    typeof end === 'number' &&
    start >= 0 &&
    end <= text.length &&
    text.slice(start, end) === excerpt
  ) {
    return { before: text.slice(0, start), mark: excerpt, after: text.slice(end), searched: false };
  }
  const idx = text.indexOf(excerpt);
  if (idx < 0) return null;
  return {
    before: text.slice(0, idx),
    mark: excerpt,
    after: text.slice(idx + excerpt.length),
    searched: true,
  };
}

/** G3 ProvenanceTab — 값 선택 → GET /provenance/{id} → GET /raw/{id}?as=text, 발췌 오프셋 하이라이트 (탭이 열릴 때만 로드) */
export function ProvenanceTab({ detail }: { detail: ComplexDetail }) {
  const items = useMemo(() => collect(detail), [detail]);
  const [selected, setSelected] = useState<string | null>(items[0]?.fact.prov ?? null);
  const prov = useProvenance(selected);
  const rawId = prov.data?.raw_document_id ?? null;
  const raw = useRawText(rawId, rawId !== null);
  const parts =
    raw.data !== undefined && prov.data
      ? highlightExcerpt(
          raw.data,
          prov.data.excerpt,
          prov.data.excerpt_start,
          prov.data.excerpt_end,
        )
      : null;

  return (
    <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
      <div className="flex flex-col gap-1">
        <h3 className="text-sm font-semibold">{t('page.G3.provenance.fields')}</h3>
        <p className="text-xs text-muted">{t('page.G3.provenance.pick')}</p>
        {items.length === 0 ? (
          <EmptyState reason={t('page.common.none')} />
        ) : (
          <ul className="flex flex-col gap-1 text-sm" aria-label={t('page.G3.provenance.fields')}>
            {items.map((item) => (
              <li key={item.key} className="flex items-center gap-2">
                <button
                  type="button"
                  aria-pressed={selected === item.fact.prov}
                  onClick={() => setSelected(item.fact.prov)}
                  className={`rounded border px-2 py-0.5 text-left ${
                    selected === item.fact.prov ? 'border-accent' : 'border-border'
                  }`}
                >
                  {item.title}
                </button>
                <FactCell
                  fact={item.fact}
                  unit={unitOf(item.fact, 'text')}
                  asof={detail.asof_date}
                  onOpenProvenance={(p) => setSelected(p)}
                />
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="flex flex-col gap-2" aria-live="polite">
        <h3 className="text-sm font-semibold">{t('page.G3.provenance.raw')}</h3>
        {prov.data ? (
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <LabelBadge label={prov.data.label} reason={prov.data.reason} />
            {prov.data.checked_at ? <span>{formatDate(prov.data.checked_at)}</span> : null}
            {prov.data.url ? (
              <a
                href={prov.data.url}
                target="_blank"
                rel="noreferrer noopener"
                className="break-all underline"
              >
                {prov.data.url}
              </a>
            ) : null}
            {rawId !== null ? (
              <a
                href={rawDocumentUrl(rawId)}
                target="_blank"
                rel="noreferrer"
                className="underline"
              >
                {t('page.G3.provenance.openFile')}
              </a>
            ) : null}
          </div>
        ) : prov.isLoading ? (
          <p className="text-sm text-muted">{t('app.loading')}</p>
        ) : null}
        {prov.data && rawId === null ? (
          <EmptyState message={t('page.G3.provenance.noRaw')}>
            {prov.data.excerpt ? (
              <blockquote className="text-fg">{prov.data.excerpt}</blockquote>
            ) : null}
          </EmptyState>
        ) : null}
        {raw.data !== undefined ? (
          parts ? (
            <>
              {parts.searched ? (
                <p className="text-xs text-muted">{t('page.G3.provenance.excerptNotFound')}</p>
              ) : null}
              <pre
                data-testid="raw-text"
                className="max-h-[60vh] overflow-auto whitespace-pre-wrap rounded border border-border bg-bg p-2 text-xs"
              >
                {parts.before}
                <mark
                  aria-label={t('page.G3.provenance.highlight')}
                  className="rounded bg-accent px-0.5 text-accent-fg"
                  ref={(el) => el?.scrollIntoView?.({ block: 'center' })}
                >
                  {parts.mark}
                </mark>
                {parts.after}
              </pre>
            </>
          ) : (
            <>
              <p className="text-xs text-muted">{t('page.G3.provenance.excerptNotFound')}</p>
              {prov.data?.excerpt ? (
                <blockquote className="border-l-2 border-border pl-2 text-sm">
                  {prov.data.excerpt}
                </blockquote>
              ) : null}
            </>
          )
        ) : raw.isLoading ? (
          <p className="text-sm text-muted">{t('app.loading')}</p>
        ) : null}
      </div>
    </div>
  );
}
