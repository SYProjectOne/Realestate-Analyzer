import { useQueryClient } from '@tanstack/react-query';
import { useId, useState } from 'react';
import { useCanWrite } from '@/api/auth';
import { ApiError } from '@/api/client';
import {
  invalidateFactViews,
  queryKeys,
  useResolveRegion,
  useUpdateRegionSelections,
} from '@/api/hooks';
import type {
  Region,
  RegionCandidate,
  RegionPatch,
  RegionPatched,
  RegionSelection,
} from '@/api/types';
import { useToast } from '@/app/toast';
import { Card, MetaText, PublishJobProgress, StatusPill } from '@/components';
import { t } from '@/i18n';
import { enumText, useDebounced } from '../_shared';
import { ERROR_BOX } from '../region-new/ui';

const DEBOUNCE_MS = 300;

const key = (s: Pick<RegionSelection, 'kind' | 'code'>) => `${s.kind}:${s.code}`;

/** 저장 전 바뀐 점: 추가·제거된 선택 */
export function selectionDiff(
  before: readonly RegionSelection[],
  after: readonly RegionSelection[],
): { added: RegionSelection[]; removed: RegionSelection[] } {
  const was = new Set(before.map(key));
  const now = new Set(after.map(key));
  return {
    added: after.filter((s) => !was.has(key(s))),
    removed: before.filter((s) => !now.has(key(s))),
  };
}

/** 선택이 그대로인 저장(이름만 — 서버가 센 추가·제거가 없고 change_event 없음) */
function nameOnly(result: RegionPatched): boolean {
  return result.added.length === 0 && result.removed.length === 0 && result.change_event === null;
}

const INPUT =
  'min-h-11 w-full rounded-xl border border-border-strong bg-surface px-3.5 py-2.5 text-base disabled:bg-subtle disabled:text-grayed';
const SMALL_BUTTON =
  'min-h-9 rounded-[10px] border border-border-strong bg-surface px-3 text-sm font-medium text-fg hover:border-fg-2 disabled:cursor-not-allowed disabled:opacity-50';

/**
 * G0-2 지역 범위 확장 (D11-7·D11-10, 계약 .8 PATCH /regions/{id} {selections, name?}) = RA "지역 추가". 목업 LivingAreas
 * "지역 범위를 넓히거나 줄일까요?"(#range).
 * 지금 선택(시도·시군구·읍면동)에 후보를 더하거나 빼고(이름도 바꿀 수 있다) 저장하면, 서버가 change_event(critical)와
 * region.expand 잡(job_id)을 만들고 그 잡이 새 리비전에서 후보 전체 rerank 를 1회 돌려 보고서 §12 "지역 추가" 장
 * (이전 리비전과 비교)을 만든다. 응답의 added·removed(서버가 센 추가·제거)를 보여 주고, 잡이 끝나면 기준일 목록
 * (새 리비전)과 사실 화면을 다시 읽는다. 마지막 선택 하나는 뺄 수 없다. 지역명은 서버 값만 쓴다.
 */
export function RegionExpandPanel({ region }: { region: Region }) {
  const canWrite = useCanWrite();
  const toast = useToast();
  const update = useUpdateRegionSelections(region.id);
  const qc = useQueryClient();
  const [selections, setSelections] = useState<RegionSelection[]>(region.selections);
  const [name, setName] = useState(region.name);
  const [query, setQuery] = useState('');
  const debounced = useDebounced(query, DEBOUNCE_MS);
  const resolve = useResolveRegion(debounced);
  const [saved, setSaved] = useState<RegionPatched | null>(null);
  const searchId = useId();
  const nameId = useId();
  const headingId = useId();
  const diff = selectionDiff(region.selections, selections);
  const renamed = name.trim() !== '' && name.trim() !== region.name;
  const dirty = diff.added.length + diff.removed.length > 0 || renamed;
  const candidates = debounced.trim().length >= 2 ? (resolve.data ?? []) : [];

  const add = (c: RegionCandidate) =>
    setSelections((prev) =>
      prev.some((s) => key(s) === key(c))
        ? prev
        : [...prev, { kind: c.kind, code: c.code, full_name: c.full_name }],
    );
  const remove = (s: RegionSelection) =>
    setSelections((prev) => (prev.length <= 1 ? prev : prev.filter((x) => key(x) !== key(s))));

  const save = () => {
    if (!dirty || !canWrite) return;
    const body: RegionPatch = renamed ? { selections, name: name.trim() } : { selections };
    update.mutate(body, {
      onSuccess: (result) => {
        setSaved(result);
        setSelections(result.region.selections);
        setName(result.region.name);
        // 계약 .9: 이름만 바꾸면 change_event null(재판정 없음). 계약 .14 F6: 발행 리비전이 있으면 이름만이어도 202 +
        // snapshot.publish 잡(보고서 표지) — 이름만인지는 선택이 바뀌었는가(added·removed)로 가른다
        toast({
          message: nameOnly(result)
            ? t('page.G0_2.expand.savedNameOnly')
            : t('page.G0_2.expand.saved'),
        });
      },
    });
  };

  const serverError =
    update.error instanceof ApiError ? update.error.detail : (update.error?.message ?? null);
  const last = selections.length <= 1;

  return (
    <Card
      as="section"
      id="range"
      aria-label={t('page.G0_2.expand.title')}
      padding="lg"
      className="flex scroll-mt-24 flex-col gap-[18px]"
    >
      <div className="flex flex-col gap-1">
        <h2 id={headingId} className="flex items-center gap-2 text-lg font-bold sm:text-[22px]">
          {t('page.G0_2.expand.title')}
        </h2>
        <p className="text-sm leading-relaxed text-muted">{t('page.G0_2.expand.intro')}</p>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <div className="flex flex-col gap-3.5">
          <div className="flex flex-col gap-2">
            <p className="text-sm font-semibold text-fg-2">{t('page.G0_2.expand.current')}</p>
            <ul aria-label={t('page.G0_2.expand.current')} className="flex flex-wrap gap-2">
              {selections.map((s) => {
                const added = diff.added.some((a) => key(a) === key(s));
                return (
                  <li
                    key={key(s)}
                    data-added={added || undefined}
                    className={`inline-flex min-h-11 items-center gap-2 rounded-full border py-1.5 pl-3.5 pr-1.5 text-[15px] font-semibold ${
                      added
                        ? 'border-accent bg-accent-soft text-accent-ink'
                        : 'border-border-strong bg-surface text-fg'
                    }`}
                  >
                    {s.full_name}
                    <span className={`text-xs font-medium ${added ? '' : 'text-muted'}`}>
                      {enumText('page.common.candidateKind', s.kind)}
                      {added ? ` · ${t('page.G0_2.expand.added')}` : ''}
                    </span>
                    <button
                      type="button"
                      data-write
                      disabled={!canWrite || last}
                      title={last ? t('page.G0_2.expand.removeLast') : undefined}
                      onClick={() => remove(s)}
                      aria-label={t('page.G0_2.expand.remove', { name: s.full_name })}
                      className="min-h-8 rounded-full border border-border-strong bg-surface px-2 text-sm font-medium text-fg hover:border-fg-2 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      ×
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
          <div className="flex flex-col gap-1.5" data-write>
            <label htmlFor={nameId} className="text-sm font-semibold text-fg-2">
              {t('page.G0_2.expand.name')}
            </label>
            <input
              id={nameId}
              type="text"
              value={name}
              maxLength={100}
              disabled={!canWrite}
              onChange={(e) => setName(e.target.value)}
              className={INPUT}
            />
          </div>
        </div>

        <div className="flex flex-col gap-2" data-write>
          <label htmlFor={searchId} className="text-sm font-semibold text-fg-2">
            {t('page.G0_2.expand.search')}
          </label>
          <input
            id={searchId}
            type="search"
            value={query}
            autoComplete="off"
            placeholder={t('page.G0.searchPlaceholder')}
            onChange={(e) => setQuery(e.target.value)}
            className={INPUT}
          />
          {debounced.trim().length >= 2 && resolve.data && candidates.length === 0 ? (
            <p className="rounded-[10px] bg-subtle p-3 text-sm text-fg-2">
              {t('page.G0_2.expand.noCandidates')}
            </p>
          ) : null}
          {candidates.length > 0 ? (
            <ul aria-label={t('page.G0_2.expand.candidates')} className="flex flex-col gap-1.5">
              {candidates.map((c) => {
                const have = selections.some((s) => key(s) === key(c));
                return (
                  <li
                    key={key(c)}
                    className="flex flex-wrap items-center gap-2 rounded-[10px] border border-border px-2.5 py-2"
                  >
                    <span className="min-w-0 flex-[1_1_160px] text-sm font-semibold">
                      {c.full_name}
                    </span>
                    <span className="rounded-md bg-chip px-2 py-0.5 text-xs text-fg-2">
                      {enumText('page.common.candidateKind', c.kind)}
                    </span>
                    <MetaText
                      kind="count"
                      className="text-xs tabular-nums text-muted"
                      k="page.G0.dongCount"
                      params={{ n: c.legal_dong_codes.length }}
                    />
                    <button
                      type="button"
                      disabled={have || !canWrite}
                      onClick={() => add(c)}
                      className={SMALL_BUTTON}
                    >
                      {have ? t('page.G0_2.expand.have') : t('page.G0_2.expand.add')}
                    </button>
                  </li>
                );
              })}
            </ul>
          ) : null}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3 border-t border-subtle pt-4" data-write>
        {diff.added.length + diff.removed.length > 0 ? (
          <span
            className="rounded-lg bg-subtle px-3 py-2 text-sm tabular-nums text-fg-2"
            data-testid="expand-diff"
          >
            <MetaText
              kind="count"
              k="page.G0_2.expand.diff"
              params={{ added: diff.added.length, removed: diff.removed.length }}
            />
          </span>
        ) : null}
        <button
          type="button"
          onClick={save}
          disabled={!dirty || !canWrite || update.isPending}
          title={canWrite ? undefined : t('auth.readOnlyHint')}
          className="min-h-11 rounded-xl bg-accent px-5 text-[15px] font-semibold text-accent-fg hover:bg-accent-ink disabled:cursor-not-allowed disabled:bg-grayed/40 disabled:text-surface"
        >
          {t('page.G0_2.expand.submit')}
        </button>
        {serverError ? (
          <p role="alert" className={ERROR_BOX}>
            {t('page.common.loadError', { detail: serverError })}
          </p>
        ) : null}
      </div>

      {saved ? (
        <div data-testid="expand-job" className="flex flex-col gap-2 rounded-xl bg-subtle p-3.5">
          <p className="text-[15px]" data-testid="expand-result">
            <MetaText
              kind="count"
              className="font-bold"
              k="page.G0_2.expand.result"
              params={{ added: saved.added.length, removed: saved.removed.length }}
            />
            {saved.added.length > 0 ? (
              <span className="ml-1.5 text-muted">
                {t('page.G0_2.expand.addedNames', {
                  names: saved.added.map((s) => s.full_name).join(', '),
                })}
              </span>
            ) : null}
            {saved.removed.length > 0 ? (
              <span className="ml-1.5 text-muted">
                {t('page.G0_2.expand.removedNames', {
                  names: saved.removed.map((s) => s.full_name).join(', '),
                })}
              </span>
            ) : null}
          </p>
          {saved.change_event ? (
            <p className="flex flex-wrap items-center gap-1.5 text-[13px] text-fg-2">
              <StatusPill tone={saved.change_event.severity === 'critical' ? 'warn' : 'neutral'}>
                {enumText('page.common.severity', saved.change_event.severity)}
              </StatusPill>
              {saved.change_event.new_text ?? ''}
            </p>
          ) : null}
          {saved.job_id !== null ? (
            <>
              {nameOnly(saved) ? (
                <p className="text-[13px] text-fg-2" data-testid="expand-name-publish">
                  {t('page.G0_2.expand.nameOnlyPublish')}
                </p>
              ) : (
                <p className="text-[13px] text-fg-2">{t('page.G0_2.expand.jobHint')}</p>
              )}
              <PublishJobProgress
                jobId={saved.job_id}
                onDone={() => {
                  void qc.invalidateQueries({ queryKey: queryKeys.snapshots(region.id) });
                  invalidateFactViews(qc);
                }}
              />
              <p className="text-xs text-muted">{t('page.G0_2.expand.jobDoneHint')}</p>
            </>
          ) : (
            <p className="text-[13px] text-fg-2" data-testid="expand-name-only">
              {t('page.G0_2.expand.nameOnly')}
            </p>
          )}
        </div>
      ) : null}
    </Card>
  );
}
