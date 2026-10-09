import { useId, useMemo, useState, type DragEvent, type ReactNode } from 'react';
import { useParams } from 'react-router';
import { useCanWrite } from '@/api/auth';
import { ApiError } from '@/api/client';
import { useRegion, useUpdateLivingAreas } from '@/api/hooks';
import type { LivingAreasUpdated, Region } from '@/api/types';
import { useToast } from '@/app/toast';
import { EmptyState, FactCell, JobProgress } from '@/components';
import { t } from '@/i18n';
import { PageShell } from '@/layout/PageShell';
import { formatCount } from '@/lib/format';
import { QueryState } from '../_shared';

export interface DraftArea {
  /** 화면 안 키(기존 생활권은 서버 id) */
  key: string;
  /** 서버 생활권 id. 새로 만든 생활권은 null */
  id: string | null;
  name: string;
  codes: string[];
}

export interface Validation {
  unassigned: string[];
  duplicated: string[];
  emptyName: boolean;
  ok: boolean;
}

/** 모든 법정동은 정확히 한 생활권에 속해야 한다(D2-3, 서버는 422) — 저장 전에 같은 규칙으로 막는다 */
export function validate(all: readonly string[], areas: readonly DraftArea[]): Validation {
  const count = new Map<string, number>();
  for (const area of areas)
    for (const code of area.codes) count.set(code, (count.get(code) ?? 0) + 1);
  const unassigned = all.filter((c) => !count.has(c));
  const duplicated = [...count.entries()].filter(([, n]) => n > 1).map(([c]) => c);
  const emptyName = areas.some((a) => a.name.trim() === '');
  return {
    unassigned,
    duplicated,
    emptyName,
    ok: unassigned.length === 0 && duplicated.length === 0 && !emptyName,
  };
}

/** codes를 target 생활권으로 옮긴다(다른 생활권에서는 뺀다) */
export function moveCodes(
  areas: DraftArea[],
  codes: readonly string[],
  targetKey: string,
): DraftArea[] {
  const moving = new Set(codes);
  return areas.map((area) => {
    const kept = area.codes.filter((c) => !moving.has(c));
    if (area.key !== targetKey) return { ...area, codes: kept };
    return { ...area, codes: [...kept, ...codes.filter((c) => !kept.includes(c))] };
  });
}

function fromRegion(region: Region): DraftArea[] {
  return region.living_areas.map((la) => ({
    key: la.id,
    id: la.id,
    name: la.name,
    codes: [...la.legal_dong_codes],
  }));
}

/**
 * G0-2 생활권 편집 `/regions/:id/living-areas` (D2-5)
 * 생활권 카드 + 법정동 목록(끌어다 놓기 또는 선택 후 이동) · 추가·이름 변경·삭제(빈 경우만) · 세대수(Fact) · 저장 → PUT
 */
export function LivingAreasPage() {
  const { id } = useParams<{ id: string }>();
  const query = useRegion(id);
  return (
    <PageShell title={t('page.G0_2.title')}>
      <p className="text-sm text-muted">{t('page.G0_2.intro')}</p>
      <QueryState query={query}>
        {(region) => <Editor key={region.id} region={region} />}
      </QueryState>
    </PageShell>
  );
}

function Editor({ region }: { region: Region }) {
  const [areas, setAreas] = useState<DraftArea[]>(() => fromRegion(region));
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const [target, setTarget] = useState<string>(region.living_areas[0]?.id ?? '');
  const [dirty, setDirty] = useState(false);
  const [saved, setSaved] = useState<LivingAreasUpdated | null>(null);
  const [nextNo, setNextNo] = useState(1);
  const update = useUpdateLivingAreas(region.id);
  const canWrite = useCanWrite();
  const toast = useToast();
  const moveId = useId();

  const allCodes = region.legal_dong_codes;
  const dongName = useMemo(() => {
    const names = new Map<string, string>();
    for (const s of region.selections) if (s.kind === 'legal_dong') names.set(s.code, s.full_name);
    return (code: string) => names.get(code) ?? code;
  }, [region.selections]);
  const households = useMemo(
    () => new Map(region.living_areas.map((la) => [la.id, la.households])),
    [region.living_areas],
  );
  const check = validate(allCodes, areas);
  // 어느 생활권에도 없는 법정동은 첫 카드 위에 따로 보여 준다
  const unassigned = check.unassigned;

  const change = (next: DraftArea[]) => {
    setAreas(next);
    setDirty(true);
    setSaved(null);
  };
  const move = (codes: readonly string[], key: string) => {
    if (!key || codes.length === 0) return;
    change(moveCodes(areas, codes, key));
    setSelected(new Set());
  };
  const toggle = (code: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });

  const onDrop = (key: string) => (event: DragEvent<HTMLElement>) => {
    event.preventDefault();
    const code = event.dataTransfer.getData('text/plain');
    if (!code) return;
    move(selected.has(code) ? [...selected] : [code], key);
  };

  const save = () => {
    if (!check.ok) return;
    update.mutate(
      {
        living_areas: areas.map((a) => ({
          id: a.id,
          name: a.name.trim(),
          legal_dong_codes: a.codes,
        })),
      },
      {
        onSuccess: (result) => {
          setSaved(result);
          setDirty(false);
          toast({ message: t('page.G0_2.saved') });
        },
      },
    );
  };

  const fieldErrors = update.error instanceof ApiError ? update.error.fieldErrors : [];

  const dong = (code: string) => (
    <li
      key={code}
      draggable
      onDragStart={(e) => e.dataTransfer.setData('text/plain', code)}
      className="flex items-center gap-2 rounded px-1 py-0.5 hover:bg-bg"
    >
      <label className="inline-flex cursor-grab items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={selected.has(code)}
          onChange={() => toggle(code)}
          aria-label={t('page.G0_2.selectDong', { name: dongName(code) })}
        />
        <span>{dongName(code)}</span>
        {dongName(code) !== code ? <span className="text-xs text-muted">{code}</span> : null}
      </label>
    </li>
  );

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2 rounded border border-border bg-surface p-2 text-sm">
        <label htmlFor={moveId} className="text-muted">
          {t('page.G0_2.moveTo')}
        </label>
        <select
          id={moveId}
          value={target}
          onChange={(e) => setTarget(e.target.value)}
          className="rounded border border-border bg-surface px-2 py-1"
        >
          {areas.map((a) => (
            <option key={a.key} value={a.key}>
              {a.name || a.key}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={() => move([...selected], target)}
          disabled={selected.size === 0}
          className="rounded border border-border px-2 py-1 disabled:opacity-50"
        >
          {t('page.G0_2.move')}
        </button>
        <span className="text-xs text-muted">{t('page.G0_2.dropHint')}</span>
        <button
          type="button"
          onClick={() => {
            const key = `new_${nextNo}`;
            change([
              ...areas,
              {
                key,
                id: null,
                name: t('page.G0_2.newName', { n: formatCount(nextNo) }),
                codes: [],
              },
            ]);
            setNextNo((n) => n + 1);
          }}
          className="ml-auto rounded border border-border px-2 py-1"
        >
          {t('page.G0_2.add')}
        </button>
      </div>

      {unassigned.length > 0 ? (
        <section
          className="rounded border border-danger p-2"
          aria-label={t('page.G0_2.unassigned', { n: formatCount(unassigned.length) })}
        >
          <p className="text-sm text-danger">
            {t('page.G0_2.unassigned', { n: formatCount(unassigned.length) })}
          </p>
          <ul className="flex flex-wrap gap-2">{unassigned.map(dong)}</ul>
        </section>
      ) : null}

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {areas.map((area) => (
          <AreaCard
            key={area.key}
            area={area}
            households={area.id ? (households.get(area.id) ?? null) : null}
            onRename={(name) => change(areas.map((a) => (a.key === area.key ? { ...a, name } : a)))}
            onDelete={() => change(areas.filter((a) => a.key !== area.key))}
            onDrop={onDrop(area.key)}
          >
            {area.codes.length === 0 ? (
              <EmptyState message={t('page.G0_2.dropHint')} />
            ) : (
              <ul className="flex flex-col gap-0.5">{area.codes.map(dong)}</ul>
            )}
          </AreaCard>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={save}
          disabled={!canWrite || !check.ok || update.isPending}
          title={canWrite ? undefined : t('auth.readOnlyHint')}
          className="rounded bg-accent px-3 py-1.5 text-sm text-accent-fg disabled:opacity-50"
        >
          {t('page.G0_2.save')}
        </button>
        {dirty ? <span className="text-xs text-muted">{t('page.G0_2.dirty')}</span> : null}
        {check.duplicated.length > 0 ? (
          <span role="alert" className="text-sm text-danger">
            {t('page.G0_2.duplicated', { n: formatCount(check.duplicated.length) })}
          </span>
        ) : null}
        {check.emptyName ? (
          <span role="alert" className="text-sm text-danger">
            {t('page.G0_2.emptyName')}
          </span>
        ) : null}
        {update.error ? (
          <div role="alert" className="text-sm text-danger">
            <p>
              {t('page.G0_2.saveError', {
                detail:
                  update.error instanceof ApiError ? update.error.detail : update.error.message,
              })}
            </p>
            {fieldErrors.length > 0 ? (
              <ul className="list-disc pl-5 text-xs">
                {fieldErrors.map((fe) => (
                  <li key={`${fe.loc.join('.')}-${fe.msg}`}>{`${fe.loc.join('.')}: ${fe.msg}`}</li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}
      </div>
      {saved ? <JobProgress jobId={String(saved.job_id)} /> : null}
    </div>
  );
}

function AreaCard({
  area,
  households,
  onRename,
  onDelete,
  onDrop,
  children,
}: {
  area: DraftArea;
  households: Region['living_areas'][number]['households'] | null;
  onRename: (name: string) => void;
  onDelete: () => void;
  onDrop: (event: DragEvent<HTMLElement>) => void;
  children: ReactNode;
}) {
  const nameId = useId();
  const empty = area.codes.length === 0;
  return (
    <section
      aria-label={area.name || area.key}
      onDragOver={(e) => e.preventDefault()}
      onDrop={onDrop}
      className="flex flex-col gap-2 rounded border border-border bg-surface p-3"
    >
      <div className="flex items-center gap-2">
        <label htmlFor={nameId} className="sr-only">
          {t('page.G0_2.areaName')}
        </label>
        <input
          id={nameId}
          value={area.name}
          onChange={(e) => onRename(e.target.value)}
          className="flex-1 rounded border border-border bg-surface px-2 py-1 font-medium"
        />
        <button
          type="button"
          onClick={onDelete}
          disabled={!empty}
          title={empty ? undefined : t('page.G0_2.deleteDisabled')}
          className="rounded border border-border px-2 py-1 text-xs disabled:opacity-50"
        >
          {t('page.G0_2.delete')}
        </button>
      </div>
      <dl className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
        <dt className="text-muted">{t('page.G0_2.households')}</dt>
        <dd>
          <FactCell fact={households} unit="households" emptyReason={t('page.common.none')} />
        </dd>
        <dt className="text-muted">{t('page.G0_2.dongs')}</dt>
        <dd>{t('page.G0_2.dongCount', { n: formatCount(area.codes.length) })}</dd>
      </dl>
      {children}
    </section>
  );
}
