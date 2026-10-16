import { useQuery } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { apiFetch, isMaterializePending } from '@/api/client';
import { useProvenance } from '@/api/hooks';
import { t, tDynamic } from '@/i18n';
import type { Provenance, ProvenanceConflict } from '@/lib/contract';
import { queryErrorText } from '@/lib/errorText';
import { formatDate } from '@/lib/format';
import { splitUnitBasis } from '@/lib/unitBasis';
import { Badge } from './Badge';
import { EmptyState } from './EmptyState';
import { ExternalLink } from './ExternalLink';
import { LabelBadge } from './LabelBadge';
import { MetaText, MetaValue } from './MetaValue';
import { RawDocumentPreview } from './RawDocumentPreview';
import {
  ProvenanceContext,
  ProvenanceSnapshotContext,
  type OpenProvenance,
} from './provenanceContext';

export interface ProvenancePanelProps {
  /** 출처 id(fp_/sc_/st_/jl_/hc_/rd_/cs_). null이면 닫힘 */
  provId: string | null;
  onClose: () => void;
  /** 보고 있는 리비전(계약 .11 F1 `?snapshot_id=`) — 발행 리비전이면 발행 순간 저장본을 본다. null 이면 생략 */
  snapshotId?: string | null;
}

/** 원문 하이라이트 창: excerpt 오프셋 앞뒤로 보여 줄 글자 수 */
const RAW_CONTEXT = 160;

/** text 안의 needle을 모두 <mark>로. needle이 없거나 못 찾으면 그대로. */
/**
 * 강등(검증 모순) 출처인가 — 계약 .9: `GET /provenance/fp_N` 은 강등 중이면 label '확인 불가'·reason '검증 모순 — …'
 * (D11-3·D12-2 읽기 오버레이). 출처 서랍에 강등 배지·해제 조건을 보인다(4차 리뷰 minor).
 */
export function isDemoted(p: { label: string; reason?: string | null }): boolean {
  return p.label === '확인 불가' && (p.reason ?? '').startsWith('검증 모순');
}

export function Highlighted({ text, needle }: { text: string; needle?: string | null }) {
  if (!needle) return <>{text}</>;
  const parts = text.split(needle);
  if (parts.length === 1) return <>{text}</>;
  const out: ReactNode[] = [];
  parts.forEach((part, index) => {
    if (index > 0) out.push(<mark key={`m${index}`}>{needle}</mark>);
    if (part) out.push(<span key={`t${index}`}>{part}</span>);
  });
  return <>{out}</>;
}

/** 원문 텍스트(GET /raw/{id}?as=text)에서 excerpt_start~end 구간을 앞뒤 문맥과 함께 하이라이트 */
function RawExcerpt({ rawId, start, end }: { rawId: number; start: number; end: number }) {
  const { data, error, isLoading } = useQuery({
    queryKey: ['raw', rawId, 'text'],
    queryFn: ({ signal }) =>
      apiFetch<string>(`/raw/${encodeURIComponent(String(rawId))}`, {
        query: { as: 'text' },
        signal,
      }),
    staleTime: Infinity,
  });
  if (isLoading) return <p className="text-muted">{t('provenance.rawLoading')}</p>;
  if (error || typeof data !== 'string')
    return <EmptyState inline message={t('provenance.rawError')} />;
  const from = Math.max(0, start - RAW_CONTEXT);
  const to = Math.min(data.length, end + RAW_CONTEXT);
  return (
    <pre
      className="max-h-64 overflow-auto whitespace-pre-wrap break-all rounded-lg bg-subtle p-2 text-[13px] leading-relaxed"
      data-testid="raw-excerpt"
    >
      {from > 0 ? '…' : ''}
      {data.slice(from, start)}
      <mark>{data.slice(start, end)}</mark>
      {data.slice(end, to)}
      {to < data.length ? '…' : ''}
    </pre>
  );
}

function ConflictItem({
  item,
  current,
  onOpen,
}: {
  item: ProvenanceConflict;
  current: boolean;
  onOpen?: (prov: string) => void;
}) {
  const excerpt = splitUnitBasis(item.excerpt);
  return (
    <li
      className={`flex flex-col gap-1 rounded-[10px] border border-border p-2.5 text-[13px] ${current ? '' : 'text-fg-2'}`}
      data-prov={item.id}
    >
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge tone={item.chosen ? 'accent' : 'muted'}>
          {item.chosen ? t('provenance.chosen') : t('provenance.notChosen')}
        </Badge>
        <span className="font-semibold text-fg">{item.value_text ?? t('empty.unknown')}</span>
        <LabelBadge label={item.label} reason={item.reason} checkedAt={item.checked_at} full />
        <span className="text-xs text-muted">
          {item.source_kind ? `${item.source_kind} · ` : null}
          <MetaText kind="rank" k="provenance.sourceRank" params={{ rank: item.source_rank }} />
        </span>
      </div>
      {excerpt.body ? (
        <blockquote className="whitespace-pre-wrap text-muted">
          <Highlighted text={excerpt.body} needle={item.value_text} />
        </blockquote>
      ) : null}
      {excerpt.unitBasis ? (
        <span className="text-muted" data-testid="conflict-unit-basis">
          <span className="text-muted">{t('provenance.unitBasis')}</span> {excerpt.unitBasis}
        </span>
      ) : null}
      <div className="flex flex-wrap gap-x-3 gap-y-1">
        {item.url ? (
          <ExternalLink href={item.url} className="break-all text-accent underline" />
        ) : null}
        {!current && onOpen ? (
          <button type="button" className="text-accent underline" onClick={() => onOpen(item.id)}>
            {t('provenance.openConflict')}
          </button>
        ) : null}
      </div>
    </li>
  );
}

function ProvenanceBody({
  data,
  onOpenConflict,
}: {
  data: Provenance;
  onOpenConflict: (prov: string) => void;
}) {
  const [showRaw, setShowRaw] = useState(false);
  const excerpt = splitUnitBasis(data.excerpt);
  const canShowRaw =
    data.raw_document_id !== null &&
    data.excerpt_start !== null &&
    data.excerpt_start !== undefined &&
    data.excerpt_end !== null &&
    data.excerpt_end !== undefined;

  // 상충 그룹 = 지금 출처(채택 여부 포함) + 같은 conflict_group의 다른 후보 전부(T5)
  const group: ProvenanceConflict[] = data.conflict_group
    ? [
        {
          id: data.id,
          value_text: data.value_text ?? null,
          label: data.label,
          reason: data.reason ?? null,
          url: data.url,
          checked_at: data.checked_at,
          source_kind: data.source_kind ?? null,
          source_rank: data.source_rank ?? 0,
          chosen: data.chosen ?? false,
          excerpt: null,
          raw_document_id: data.raw_document_id,
        },
        ...data.conflicts,
      ]
    : data.conflicts;

  return (
    <dl className="grid grid-cols-[minmax(84px,120px)_minmax(0,1fr)] gap-x-3.5 gap-y-2.5 text-sm [&>dt]:text-muted">
      {data.entity || data.field ? (
        <>
          {/* 목업 §3 '무엇' 줄(N5) — 예전에는 이름 없는 작은 글씨 */}
          <dt>{t('provenance.what')}</dt>
          <dd data-testid="provenance-what">
            {[data.entity, data.field].filter(Boolean).join(' · ')}
          </dd>
        </>
      ) : null}
      {data.value_text ? (
        <>
          <dt>{t('provenance.value')}</dt>
          <dd className="font-bold tabular-nums">{data.value_text}</dd>
        </>
      ) : null}
      <dt>{t('provenance.label')}</dt>
      <dd>
        <LabelBadge label={data.label} reason={data.reason} checkedAt={data.checked_at} full />
      </dd>
      {isDemoted(data) ? (
        <dd
          className="col-span-2 flex flex-col gap-1.5 rounded-[10px] border border-warn-border bg-warn-soft px-3 py-2.5 text-[13px] text-warn-ink"
          data-testid="provenance-demoted"
        >
          <span>
            <Badge tone="cautionSolid">{t('provenance.demoted')}</Badge>
          </span>
          <span>{t('provenance.demotedHint')}</span>
        </dd>
      ) : null}
      <dt>{t('provenance.checkedAt')}</dt>
      <dd>{data.checked_at ? formatDate(data.checked_at) : <EmptyState inline />}</dd>
      <dt>{t('provenance.url')}</dt>
      <dd className="break-all">
        {data.url ? (
          <ExternalLink href={data.url} className="text-accent underline" />
        ) : (
          <EmptyState inline />
        )}
      </dd>
      {data.source_kind ? (
        <>
          <dt>{t('provenance.source')}</dt>
          <dd>
            {data.source_kind}
            {data.source_rank !== null && data.source_rank !== undefined ? (
              <>
                {' · '}
                <MetaText
                  kind="rank"
                  k="provenance.sourceRank"
                  params={{ rank: data.source_rank }}
                />
              </>
            ) : null}
          </dd>
        </>
      ) : null}
      {data.http_status !== null && data.http_status !== undefined ? (
        <>
          <dt>{t('provenance.httpStatus')}</dt>
          <dd>
            <MetaValue kind="status" value={data.http_status} as="plain" />
          </dd>
        </>
      ) : null}
      {data.formula_text ? (
        <>
          <dt>{t('provenance.formula')}</dt>
          <dd className="whitespace-pre-wrap">{data.formula_text}</dd>
        </>
      ) : null}
      {data.judgment_seq !== null && data.judgment_seq !== undefined ? (
        <>
          <dt>{t('provenance.judgment')}</dt>
          <dd>
            {'#'}
            <MetaValue kind="seq" value={data.judgment_seq} as="plain" />
          </dd>
        </>
      ) : null}
      <dt>{t('provenance.excerpt')}</dt>
      <dd className="flex flex-col gap-1">
        {excerpt.body ? (
          <blockquote
            className="whitespace-pre-wrap rounded-lg bg-subtle p-2.5 text-[13px] leading-relaxed"
            data-testid="provenance-excerpt"
          >
            <Highlighted text={excerpt.body} needle={data.value_text} />
          </blockquote>
        ) : (
          <EmptyState inline />
        )}
        {canShowRaw ? (
          <>
            <button
              type="button"
              aria-expanded={showRaw}
              onClick={() => setShowRaw((prev) => !prev)}
              className="min-h-8 self-start rounded-lg border border-border-strong bg-surface px-2.5 py-1 text-[13px] font-medium text-fg-2 hover:text-fg"
            >
              {showRaw ? t('provenance.rawTextHide') : t('provenance.rawText')}
            </button>
            {showRaw ? (
              <RawExcerpt
                rawId={data.raw_document_id as number}
                start={data.excerpt_start as number}
                end={data.excerpt_end as number}
              />
            ) : null}
          </>
        ) : null}
      </dd>
      {excerpt.unitBasis ? (
        // 계약 .16 F6(D21-1): 공고문 금액 표 단위 환산 근거(표 머리 줄) — 발췌 끝 '[단위 근거]' 줄을 따로
        <>
          <dt>{t('provenance.unitBasis')}</dt>
          <dd className="whitespace-pre-wrap" data-testid="provenance-unit-basis">
            {excerpt.unitBasis}
          </dd>
        </>
      ) : null}
      <dt>{t('provenance.conflicts')}</dt>
      <dd>
        {data.conflicts.length === 0 ? (
          t('provenance.noConflicts')
        ) : (
          <ul aria-label={t('provenance.conflicts')} className="flex flex-col gap-2">
            {group.map((item) => (
              <ConflictItem
                key={item.id}
                item={item}
                current={item.id === data.id}
                onOpen={onOpenConflict}
              />
            ))}
          </ul>
        )}
      </dd>
      {data.raw_document_id !== null ? (
        <>
          {/* 목업 §3: '원문 파일' 줄 이름을 보이게(예전 숨김 제목) */}
          <dt>{t('provenance.rawDocument')}</dt>
          <dd>
            <RawDocumentPreview rawId={data.raw_document_id as unknown as number} />
          </dd>
        </>
      ) : null}
    </dl>
  );
}

/**
 * 출처 패널(오른쪽 서랍): GET /provenance/{id} → 값·라벨(사유)·확인일·원문 주소·출처 종류/순위·HTTP 상태·
 * 산출식·원문 발췌(값 하이라이트, 원문 텍스트 오프셋 하이라이트)·상충 그룹(채택/미채택)·원문 미리보기·저장(Bearer fetch).
 * 보통 직접 쓰지 않고 앱 루트의 ProvenanceProvider가 FactCell 클릭으로 연다.
 */
export function ProvenancePanel({ provId, onClose, snapshotId = null }: ProvenancePanelProps) {
  // 상충 후보의 "이 출처 열기" → 같은 패널에서 그 출처로 이동(같은 리비전 — F1: 충돌 출처 클릭 포함)
  const [shown, setShown] = useState<{ from: string | null; id: string } | null>(null);
  const active = shown && shown.from === provId ? shown.id : provId;
  const query = useProvenance(active, snapshotId);
  const data = query.data as Provenance | undefined;
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!provId) return;
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [provId, onClose]);

  if (!provId) return null;

  return (
    <aside
      role="dialog"
      aria-modal="false"
      aria-label={t('provenance.title')}
      data-prov={active ?? undefined}
      className="fixed inset-y-0 right-0 z-40 flex w-full flex-col overflow-y-auto border-l border-border-strong bg-surface text-fg shadow-2xl sm:max-w-[460px] sm:rounded-l-2xl"
    >
      <div className="sticky top-0 z-10 flex items-center gap-2.5 border-b border-border bg-surface px-[18px] py-4">
        <h2 className="min-w-0 flex-1 text-lg font-bold">{t('provenance.title')}</h2>
        {data ? (
          <span
            className="rounded-md bg-chip px-2 py-0.5 text-xs text-fg-2"
            data-testid="provenance-kind"
          >
            {tDynamic(`provenance.kind.${data.kind}`, data.id)}
          </span>
        ) : null}
        <button
          ref={closeRef}
          type="button"
          onClick={onClose}
          className="min-h-9 rounded-[10px] border border-border-strong bg-surface px-3 text-sm font-semibold text-fg"
        >
          {t('provenance.close')}
        </button>
      </div>
      <div className="flex flex-1 flex-col gap-3 px-[18px] pb-4 pt-3">
        {query.isLoading ? (
          <p role="status" className="text-sm text-muted">
            {isMaterializePending(query.failureReason)
              ? t('page.common.materializePending')
              : t('app.loading')}
          </p>
        ) : null}
        {query.error ? (
          <EmptyState
            message={
              isMaterializePending(query.error) ||
              (query.error as { code?: string }).code === 'stored_view_mismatch'
                ? queryErrorText(query.error)
                : t('provenance.error', { detail: query.error.message })
            }
          />
        ) : null}
        {data ? (
          <ProvenanceBody
            key={data.id}
            data={data}
            onOpenConflict={(id) => setShown({ from: provId, id })}
          />
        ) : null}
      </div>
      <p className="border-t border-warn-border bg-warn-soft px-[18px] py-3 text-xs text-warn-ink">
        {t('provenance.kindsNote')}
      </p>
    </aside>
  );
}

/**
 * 앱 루트에 한 번. FactCell이 context로 openProvenance(prov[, 리비전])를 부르면 패널이 열린다.
 * 조회 리비전은 **여는 순간** 정한다(그 Fact 가 나온 리비전 — 넘기지 않으면 그때 보고 있던 리비전). 연 채로 화면 리비전이
 * 바뀌어도(발행 뒤 새 기본 리비전·헤더 변경) 서랍은 따라가지 않는다 — 새 리비전 저장본에 그 출처가 없으면 404 였다(7차 minor 17).
 */
export function ProvenanceProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState<{ provId: string; snapshotId: string | null } | null>(null);
  /** 지금 보고 있는 리비전(AppLayout 이 알린다) — 렌더에 쓰지 않고 열 때만 읽는다 */
  const viewing = useRef<string | null>(null);
  const setViewing = useCallback((sid: string | null) => {
    viewing.current = sid;
  }, []);
  const openProvenance = useCallback<OpenProvenance>((provId, snapshotId) => {
    setOpen({ provId, snapshotId: snapshotId === undefined ? viewing.current : snapshotId });
  }, []);
  const close = useCallback(() => setOpen(null), []);
  const panel = useMemo(
    () => (
      <ProvenancePanel
        provId={open?.provId ?? null}
        onClose={close}
        snapshotId={open?.snapshotId ?? null}
      />
    ),
    [open, close],
  );
  return (
    <ProvenanceContext.Provider value={openProvenance}>
      <ProvenanceSnapshotContext.Provider value={setViewing}>
        {children}
        {panel}
      </ProvenanceSnapshotContext.Provider>
    </ProvenanceContext.Provider>
  );
}
