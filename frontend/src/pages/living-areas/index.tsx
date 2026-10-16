import { useId, useMemo, useState, type DragEvent, type ReactNode } from 'react';
import { useParams } from 'react-router';
import { useCanWrite } from '@/api/auth';
import { ApiError } from '@/api/client';
import { useRegion, useUpdateLivingAreas } from '@/api/hooks';
import type { LivingAreasUpdated, Region } from '@/api/types';
import { useToast } from '@/app/toast';
import { Card, FactCell, MetaText, PublishJobProgress } from '@/components';
import { t } from '@/i18n';
import { PageShell } from '@/layout/PageShell';
import { metaText } from '@/lib/meta';
import { QueryState } from '../_shared';
import { Crumbs } from '../region-new/Crumbs';
import { ERROR_BOX } from '../region-new/ui';
import { RegionExpandPanel } from './RegionExpandPanel';

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

/** 카드 안에서 처음 보이는 법정동 수(목업: 5개 + '나머지 n개 더 보기') */
export const DONG_PREVIEW = 5;

/**
 * G0-2 생활권 편집 `/regions/:id/living-areas` (D2-5, 목업 LivingAreas)
 * 머리 '생활권이 뭐예요?' 한 줄 답 · 옮기기 도구줄 · 생활권 카드(법정동 끌어다 놓기 또는 선택 후 이동) · 추가·이름 변경·
 * 삭제(빈 경우만) · 세대수(Fact) · 저장(화면 아래 붙는 줄) → PUT · 지역 범위 확장(#range)
 */
export function LivingAreasPage() {
  const { id } = useParams<{ id: string }>();
  const query = useRegion(id);
  return (
    <div className="flex flex-col gap-4">
      <Crumbs
        items={query.data ? [query.data.name, t('page.G0_2.crumb')] : [t('page.G0_2.crumb')]}
      />
      <PageShell title={t('page.G0_2.title')}>
        <p
          data-testid="living-area-answer"
          className="rounded-xl border border-info-border bg-info-soft px-4 py-3 text-base leading-relaxed text-fg sm:text-[17px]"
        >
          <b className="mr-1.5">{t('page.G0_2.whatIs')}</b>
          {t('page.G0_2.answer')}
        </p>
        <QueryState query={query}>
          {(region) => (
            <>
              <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
                <p className="text-[15px] text-fg-2">{t('page.G0_2.intro')}</p>
                <div className="flex flex-col gap-1 text-sm text-muted">
                  <MetaText
                    kind="count"
                    className="tabular-nums"
                    k="page.G0_2.summary"
                    params={{
                      areas: region.living_areas.length,
                      dongs: region.legal_dong_codes.length,
                    }}
                  />
                  <a href="#range" className="text-accent underline underline-offset-2">
                    {t('page.G0_2.toRange')}
                  </a>
                </div>
              </div>
              <Editor key={region.id} region={region} />
              <RegionExpandPanel key={`expand-${region.id}`} region={region} />
              <p className="border-t border-border pt-4 text-[13px] text-muted">
                {t('page.G0_2.footnote')}
              </p>
            </>
          )}
        </QueryState>
      </PageShell>
    </div>
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

  const dong = (code: string) => {
    const label = dongName(code);
    const on = selected.has(code);
    return (
      <li key={code} draggable onDragStart={(e) => e.dataTransfer.setData('text/plain', code)}>
        <label
          data-selected={on || undefined}
          className={`flex min-h-9 cursor-grab items-center gap-2 rounded-lg px-2 py-1.5 text-sm ${
            on ? 'bg-accent-soft font-semibold' : 'hover:bg-bg'
          }`}
        >
          <input
            type="checkbox"
            checked={on}
            onChange={() => toggle(code)}
            aria-label={t('page.G0_2.selectDong', { name: label })}
            className="size-4 accent-accent"
          />
          <span className={label === code ? 'tabular-nums' : undefined}>{label}</span>
          {label !== code ? (
            <span className="ml-auto text-[11px] tabular-nums text-muted">{code}</span>
          ) : null}
        </label>
      </li>
    );
  };

  return (
    <div className="flex flex-col gap-4">
      <Card
        padding="sm"
        className="flex flex-wrap items-center gap-x-3 gap-y-2.5 shadow-[0_6px_18px_rgb(20_24_31/0.06)]"
        data-testid="move-toolbar"
      >
        <MetaText
          kind="count"
          className="text-[15px] font-semibold"
          k="page.G0_2.selectedCount"
          params={{ n: selected.size }}
        />
        <label htmlFor={moveId} className="ml-1 text-sm font-semibold text-fg-2">
          {t('page.G0_2.moveTo')}
        </label>
        <select
          id={moveId}
          value={target}
          onChange={(e) => setTarget(e.target.value)}
          className="min-h-11 rounded-[10px] border border-border-strong bg-surface px-3 py-2 text-[15px]"
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
          className="min-h-11 rounded-xl bg-accent px-4 text-[15px] font-semibold text-accent-fg hover:bg-accent-ink disabled:cursor-not-allowed disabled:bg-grayed/40 disabled:text-surface"
        >
          {t('page.G0_2.move')}
        </button>
        <span className="inline-flex items-center gap-1.5 text-[13px] text-muted">
          <svg
            aria-hidden
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
          >
            <path d="M9 5h.01M9 12h.01M9 19h.01M15 5h.01M15 12h.01M15 19h.01" />
          </svg>
          {t('page.G0_2.dropHint')}
        </span>
        <button
          type="button"
          onClick={() => {
            const key = `new_${nextNo}`;
            change([
              ...areas,
              {
                key,
                id: null,
                name: metaText('page.G0_2.newName', { n: nextNo }),
                codes: [],
              },
            ]);
            setNextNo((n) => n + 1);
          }}
          className="ml-auto inline-flex min-h-11 items-center gap-1.5 rounded-[10px] border border-border-strong bg-surface px-3.5 text-sm font-medium text-fg hover:border-fg-2"
        >
          <svg
            aria-hidden
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.2"
            strokeLinecap="round"
          >
            <path d="M12 5v14" />
            <path d="M5 12h14" />
          </svg>
          {t('page.G0_2.add')}
        </button>
      </Card>

      {unassigned.length > 0 ? (
        <section
          className="flex flex-col gap-2 rounded-[14px] border-2 border-danger bg-danger/5 p-3.5"
          aria-label={metaText('page.G0_2.unassigned', { n: unassigned.length })}
        >
          <p className="text-[15px] font-bold text-danger">
            <MetaText kind="count" k="page.G0_2.unassigned" params={{ n: unassigned.length }} />
          </p>
          <ul className="flex flex-wrap gap-1.5">{unassigned.map(dong)}</ul>
        </section>
      ) : null}

      <section
        aria-label={t('page.G0_2.cards')}
        className="grid items-start gap-4 md:grid-cols-2 xl:grid-cols-3"
      >
        {areas.map((area) => (
          <AreaCard
            key={area.key}
            area={area}
            active={area.codes.some((c) => selected.has(c))}
            households={area.id ? (households.get(area.id) ?? null) : null}
            onRename={(name) => change(areas.map((a) => (a.key === area.key ? { ...a, name } : a)))}
            onDelete={() => change(areas.filter((a) => a.key !== area.key))}
            onDrop={onDrop(area.key)}
            renderDong={dong}
          />
        ))}
      </section>

      <Card
        padding="sm"
        data-testid="save-bar"
        className="sticky bottom-11 z-20 flex flex-wrap items-center gap-3 px-4 shadow-[0_-6px_18px_rgb(20_24_31/0.08)]"
      >
        <button
          type="button"
          onClick={save}
          disabled={!canWrite || !check.ok || update.isPending}
          title={canWrite ? undefined : t('auth.readOnlyHint')}
          className="min-h-11 rounded-xl bg-accent px-5 text-[15px] font-semibold text-accent-fg hover:bg-accent-ink disabled:cursor-not-allowed disabled:bg-grayed/40 disabled:text-surface"
        >
          {t('page.G0_2.save')}
        </button>
        {dirty ? (
          <span className="inline-flex items-center gap-1.5 rounded-lg bg-warn-soft px-2.5 py-1.5 text-sm font-semibold text-warn-ink">
            <span aria-hidden className="size-2 rounded-full bg-warn" />
            {t('page.G0_2.dirty')}
          </span>
        ) : null}
        {!canWrite ? (
          <span className="text-[13px] text-muted">{t('auth.readOnlyHint')}</span>
        ) : (
          <span className="text-[13px] text-muted">{t('page.G0_2.saveNote')}</span>
        )}
        {check.duplicated.length > 0 ? (
          <span role="alert" className={ERROR_BOX}>
            <MetaText
              kind="count"
              k="page.G0_2.duplicated"
              params={{ n: check.duplicated.length }}
            />
          </span>
        ) : null}
        {check.emptyName ? (
          <span role="alert" className={ERROR_BOX}>
            {t('page.G0_2.emptyName')}
          </span>
        ) : null}
        {update.error ? (
          <div role="alert" className={`flex w-full flex-col gap-1 ${ERROR_BOX}`}>
            <p>
              {t('page.G0_2.saveError', {
                detail:
                  update.error instanceof ApiError ? update.error.detail : update.error.message,
              })}
            </p>
            {fieldErrors.length > 0 ? (
              <ul className="list-disc pl-5 text-[13px]">
                {fieldErrors.map((fe) => (
                  <li key={`${fe.loc.join('.')}-${fe.msg}`}>{`${fe.loc.join('.')}: ${fe.msg}`}</li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}
      </Card>
      {saved ? (
        <div className="rounded-xl bg-subtle p-3.5">
          <PublishJobProgress jobId={saved.job_id} />
        </div>
      ) : null}
    </div>
  );
}

function AreaCard({
  area,
  active,
  households,
  onRename,
  onDelete,
  onDrop,
  renderDong,
}: {
  area: DraftArea;
  /** 고른 동이 이 카드에 있다(목업: 주색 테두리) */
  active: boolean;
  households: Region['living_areas'][number]['households'] | null;
  onRename: (name: string) => void;
  onDelete: () => void;
  onDrop: (event: DragEvent<HTMLElement>) => void;
  renderDong: (code: string) => ReactNode;
}) {
  const nameId = useId();
  const [all, setAll] = useState(false);
  const empty = area.codes.length === 0;
  const fresh = area.id === null;
  const shown = all ? area.codes : area.codes.slice(0, DONG_PREVIEW);
  const rest = area.codes.length - DONG_PREVIEW;
  return (
    <section
      aria-label={area.name || area.key}
      data-new={fresh || undefined}
      data-active={active || undefined}
      onDragOver={(e) => e.preventDefault()}
      onDrop={onDrop}
      className={`flex flex-col gap-2.5 rounded-2xl p-4 ${
        active
          ? 'border-2 border-accent bg-surface'
          : fresh
            ? 'border-2 border-dashed border-accent/60 bg-accent-soft/20'
            : 'border border-border bg-surface'
      }`}
    >
      <div className="flex items-center gap-2">
        <label htmlFor={nameId} className="sr-only">
          {t('page.G0_2.areaName')}
        </label>
        <input
          id={nameId}
          value={area.name}
          onChange={(e) => onRename(e.target.value)}
          className="min-h-11 min-w-0 flex-1 rounded-xl border border-border-strong bg-surface px-3 py-2 text-base font-bold"
        />
        <button
          type="button"
          onClick={onDelete}
          disabled={!empty}
          title={empty ? undefined : t('page.G0_2.deleteDisabled')}
          className="min-h-11 shrink-0 rounded-[10px] border border-border-strong bg-surface px-3 text-sm font-medium text-fg hover:border-fg-2 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {t('page.G0_2.delete')}
        </button>
      </div>
      <dl className="flex flex-wrap items-center gap-x-3.5 gap-y-1 text-[13px]">
        <dt className="text-muted">{t('page.G0_2.households')}</dt>
        <dd className="font-semibold text-fg">
          <FactCell fact={households} unit="households" emptyReason={t('page.common.none')} />
        </dd>
        <dt className="text-muted">{t('page.G0_2.dongs')}</dt>
        <dd className="font-semibold text-fg">
          <MetaText kind="count" k="page.G0_2.dongCount" params={{ n: area.codes.length }} />
        </dd>
      </dl>
      {empty ? (
        <p className="rounded-xl border-2 border-dashed border-grayed px-3.5 py-5 text-center text-sm leading-relaxed text-muted">
          {t('page.G0_2.dropEmpty')}
        </p>
      ) : (
        <>
          <ul className="flex flex-col gap-0.5">{shown.map(renderDong)}</ul>
          {rest > 0 ? (
            <button
              type="button"
              aria-expanded={all}
              onClick={() => setAll((v) => !v)}
              className="min-h-8 self-start px-2 py-1.5 text-left text-[13px] text-accent hover:underline"
            >
              {all ? (
                t('page.G0_2.less')
              ) : (
                <MetaText kind="count" k="page.G0_2.more" params={{ n: rest }} />
              )}
            </button>
          ) : null}
        </>
      )}
    </section>
  );
}
