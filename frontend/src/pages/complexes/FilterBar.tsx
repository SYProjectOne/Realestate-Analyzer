import { useEffect, useId, useState } from 'react';
import { INTAKE_STATUSES, JUDGE_SCOPES, type LivingArea } from '@/api/types';
import { Card, MetaText, Term, type GlossaryKey } from '@/components';
import { t, type TKey } from '@/i18n';
import { enumText } from '../_shared';
import {
  FILTER_KEYS,
  isSortPreset,
  SORT_PRESETS,
  type FilterKey,
  type FilterValues,
} from './params';

const INCLUSION = [
  'private_sale_apt',
  'public_sale',
  'public_rental',
  'private_rental',
  'non_apartment',
  'out_of_scope',
  'manual_review',
  '범위 경계',
  '미분류',
] as const;
const SCOPES = JUDGE_SCOPES;
const LAND_TYPES = ['공공택지', '민간택지'] as const;

interface Option {
  value: string;
  label: string;
}

/**
 * 필터 칸 이름 옆 용어 '?'(ListTable 보드: 접수 상태 · 생활권 · 단지 종류 · 점수 계산 범위). 같은 화면에서 같은 용어 '?'는
 * 한 번(30-proposal §7-1) — 표 머리에 '?'가 있는 용어(접수 상태·생활권·단지 종류)는 표 보기에서 필터에 달지 않는다.
 */
const TERM_OF: Partial<Record<FilterKey, GlossaryKey>> = {
  intake_status: 'intake_status',
  living_area: 'living_area',
  inclusion_class: 'inclusion',
  judge_scope: 'judge_scope',
};
/** 표 머리에도 있는 용어 */
const TABLE_TERMS: ReadonlySet<FilterKey> = new Set([
  'intake_status',
  'living_area',
  'inclusion_class',
]);

/** 입력칸 예시(지역 이름·단지 이름을 박지 않는다 — 규칙 15) */
const PLACEHOLDER: Partial<Record<FilterKey, TKey>> = {
  q: 'page.G2.placeholder.q',
  price_min: 'page.G2.placeholder.price_min',
  price_max: 'page.G2.placeholder.price_max',
  move_in_year: 'page.G2.placeholder.move_in_year',
};

const inputClass =
  'min-h-10 rounded-[10px] border border-border-strong bg-surface px-3 py-1.5 text-sm text-fg';

function Field({
  name,
  value,
  onChange,
  options,
  type = 'text',
  inputMode,
  wide = false,
  terms = true,
}: {
  name: FilterKey;
  value: string;
  onChange: (key: FilterKey, value: string) => void;
  options?: Option[];
  type?: 'text' | 'date' | 'number';
  inputMode?: 'decimal' | 'numeric';
  wide?: boolean;
  /** false 면 표 머리에도 있는 용어 '?'를 달지 않는다(표 보기) */
  terms?: boolean;
}) {
  const id = useId();
  const label = t(`page.G2.filter.${name}` as TKey);
  const term = terms || !TABLE_TERMS.has(name) ? TERM_OF[name] : undefined;
  const placeholder = PLACEHOLDER[name];
  return (
    <span className={`flex flex-col gap-1 text-xs ${wide ? 'min-w-0 flex-[1_1_220px]' : ''}`}>
      <span className="inline-flex items-center gap-1">
        <label htmlFor={id} className="text-[13px] text-fg-2">
          {label}
        </label>
        {term ? <Term k={term} /> : null}
      </span>
      {options ? (
        <select
          id={id}
          value={value}
          onChange={(e) => onChange(name, e.target.value)}
          className={inputClass}
        >
          <option value="">{t('page.common.all')}</option>
          {options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      ) : (
        <input
          id={id}
          type={type}
          value={value}
          inputMode={inputMode}
          placeholder={placeholder ? t(placeholder) : undefined}
          step={type === 'number' ? 'any' : undefined}
          onChange={(e) => onChange(name, e.target.value)}
          className={`${inputClass} ${wide ? 'w-full' : 'w-36'}`}
        />
      )}
    </span>
  );
}

export interface FilterBarProps {
  values: FilterValues;
  livingAreas: LivingArea[];
  onChange: (key: FilterKey, value: string) => void;
  onReset: () => void;
  /** 모바일(≤768px): 단지명 + 칩 + '필터' 버튼 → 전체 화면 시트(R9-UI P5) */
  mobile?: boolean;
  /** 카드 보기 정렬 상자(List 보드 LS-2) — 주면 보인다 */
  sort?: { value: string; onChange: (sort: string) => void };
  /** false(표 보기): 표 머리에도 있는 용어 '?'는 필터에 달지 않는다(같은 용어 '?'는 화면에 한 번) */
  terms?: boolean;
}

/** 늘 보이는 핵심 필터(단지 이름·접수 상태·생활권) + 칩 줄(지금 접수 가능 · 이 날짜 전에 되팔 수 있게 됨) */
export const PRIMARY_FILTERS = ['q', 'intake_status', 'living_area', 'resale_end_before'] as const;
/** '필터 더 보기'(1클릭) 안의 필터 6칸 — 값이 있으면 자동으로 펼친다 */
export const MORE_FILTERS = [
  'land_type',
  'price_min',
  'price_max',
  'move_in_year',
  'inclusion_class',
  'judge_scope',
] as const satisfies readonly FilterKey[];

/** 지금 접수 가능 칩이 거는 값(계약 IntakeStatus) */
const OPEN_NOW = '가능';

/**
 * G2 FilterBar(R11 List·ListTable 보드) — 핵심 3칸 + 칩 줄(지금 접수 가능 · 이 날짜 전에 되팔 수 있게 됨 (전매 종료)) +
 * '필터 더 보기'(땅 종류·가격·입주 연도·단지 종류·점수 계산 범위). 칩은 필터 키가 있는 것만(고침 LS-1). 값은 URL 쿼리.
 * 접어도 적용 중인 필터 개수가 버튼에 보이고, 숨은 필터에 값이 있으면 펼친 채로 연다(30-proposal §5-4).
 */
export function FilterBar({
  values,
  livingAreas,
  onChange,
  onReset,
  mobile = false,
  sort,
  terms = true,
}: FilterBarProps) {
  if (mobile) {
    return (
      <MobileFilterBar
        values={values}
        livingAreas={livingAreas}
        onChange={onChange}
        onReset={onReset}
      />
    );
  }
  return (
    <DesktopFilterBar
      values={values}
      livingAreas={livingAreas}
      onChange={onChange}
      onReset={onReset}
      sort={sort}
      terms={terms}
    />
  );
}

/** 지금 접수 가능 칩(aria-pressed) */
function OpenNowChip({ values, onChange }: Pick<FilterBarProps, 'values' | 'onChange'>) {
  const openNow = values.intake_status === OPEN_NOW;
  return (
    <button
      type="button"
      aria-pressed={openNow}
      onClick={() => onChange('intake_status', openNow ? '' : OPEN_NOW)}
      className={`min-h-10 rounded-full border px-4 py-1.5 text-sm font-semibold ${
        openNow
          ? 'border-transparent bg-accent text-accent-fg'
          : 'border-border-strong bg-surface text-fg-2 hover:border-accent'
      }`}
    >
      {openNow ? t('page.G2.openNowChipOff') : t('page.G2.openNowChip')}
    </button>
  );
}

/** 카드 보기 정렬 상자 — 값 = 정렬 키(LS-3), 표에서 고른 다른 정렬은 '표에서 고른 정렬' */
function SortSelect({ value, onChange }: { value: string; onChange: (sort: string) => void }) {
  const id = useId();
  return (
    <span className="flex flex-col gap-1 text-xs">
      <label htmlFor={id} className="text-[13px] text-fg-2">
        {t('page.G2.sort.label')}
      </label>
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={inputClass}
        data-testid="sort-select"
      >
        {SORT_PRESETS.map((key) => (
          <option key={key} value={key}>
            {t(`page.G2.sort.${key}`)}
          </option>
        ))}
        {isSortPreset(value) ? null : <option value={value}>{t('page.G2.sort.other')}</option>}
      </select>
    </span>
  );
}

/**
 * 모바일 필터(30-proposal §6-1): 단지 이름 + 지금 접수 가능 칩 + '필터 (적용 n)' → 전체 화면 시트(필터 10칸, Esc·적용으로 닫힘).
 * 값은 바뀔 때마다 URL 쿼리(데스크톱과 같다) — '적용'은 시트를 닫는다.
 */
function MobileFilterBar({ values, livingAreas, onChange, onReset }: FilterBarProps) {
  const v = (k: FilterKey) => values[k] ?? '';
  const [open, setOpen] = useState(false);
  const applied = FILTER_KEYS.filter((k) => k !== 'q' && !!values[k]).length;
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open]);
  return (
    <Card padding="sm" className="flex flex-col gap-2">
      <form
        role="search"
        aria-label={t('page.G2.filters')}
        className="flex flex-col gap-2"
        onSubmit={(e) => e.preventDefault()}
      >
        <div className="flex flex-wrap items-end gap-2">
          <Field name="q" value={v('q')} onChange={onChange} wide />
          <button
            type="button"
            aria-haspopup="dialog"
            onClick={() => setOpen(true)}
            className="min-h-10 rounded-[10px] border border-border-strong px-3 py-1.5 text-sm font-semibold"
          >
            <MetaText kind="count" k="page.G2.card.filterSheet" params={{ n: applied }} />
          </button>
        </div>
        <span className="self-start">
          <OpenNowChip values={values} onChange={onChange} />
        </span>
        {open ? (
          <div
            role="dialog"
            aria-modal="true"
            aria-label={t('page.G2.filters')}
            className="fixed inset-0 z-50 flex flex-col gap-3 overflow-auto bg-bg p-4"
          >
            <h2 className="text-lg font-bold">{t('page.G2.filters')}</h2>
            <div className="flex flex-col gap-3">
              <Field name="q" value={v('q')} onChange={onChange} wide />
              <PrimarySelects values={values} livingAreas={livingAreas} onChange={onChange} />
              <Field
                name="resale_end_before"
                type="date"
                value={v('resale_end_before')}
                onChange={onChange}
              />
              <MoreFields values={values} onChange={onChange} />
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="min-h-11 flex-1 rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-accent-fg"
              >
                {t('page.G2.card.filterApply')}
              </button>
              <button
                type="button"
                onClick={onReset}
                className="min-h-11 rounded-xl border border-border-strong px-4 py-2 text-sm"
              >
                {t('page.G2.card.filterReset')}
              </button>
            </div>
          </div>
        ) : null}
      </form>
    </Card>
  );
}

/** 접수 상태·생활권(핵심 필터 중 선택 2칸) */
function PrimarySelects({
  values,
  livingAreas,
  onChange,
  terms = true,
}: Pick<FilterBarProps, 'values' | 'livingAreas' | 'onChange' | 'terms'>) {
  const v = (k: FilterKey) => values[k] ?? '';
  return (
    <>
      <Field
        name="intake_status"
        value={v('intake_status')}
        onChange={onChange}
        terms={terms}
        options={INTAKE_STATUSES.map((s) => ({ value: s, label: enumText('intake.status', s) }))}
      />
      <Field
        name="living_area"
        value={v('living_area')}
        onChange={onChange}
        terms={terms}
        options={livingAreas.map((la) => ({ value: la.id, label: la.name }))}
      />
    </>
  );
}

/** '필터 더 보기' 6칸 */
function MoreFields({
  values,
  onChange,
  terms = true,
}: Pick<FilterBarProps, 'values' | 'onChange' | 'terms'>) {
  const v = (k: FilterKey) => values[k] ?? '';
  return (
    <>
      <Field
        name="land_type"
        value={v('land_type')}
        onChange={onChange}
        terms={terms}
        options={LAND_TYPES.map((s) => ({ value: s, label: enumText('page.G2.landType', s) }))}
      />
      <Field
        name="price_min"
        type="number"
        inputMode="decimal"
        value={v('price_min')}
        onChange={onChange}
      />
      <Field
        name="price_max"
        type="number"
        inputMode="decimal"
        value={v('price_max')}
        onChange={onChange}
      />
      <Field
        name="move_in_year"
        type="number"
        inputMode="numeric"
        value={v('move_in_year')}
        onChange={onChange}
      />
      <Field
        name="inclusion_class"
        value={v('inclusion_class')}
        onChange={onChange}
        terms={terms}
        options={INCLUSION.map((s) => ({ value: s, label: enumText('page.common.inclusion', s) }))}
      />
      <Field
        name="judge_scope"
        value={v('judge_scope')}
        onChange={onChange}
        terms={terms}
        options={SCOPES.map((s) => ({ value: s, label: enumText('page.common.judgeScope', s) }))}
      />
    </>
  );
}

function DesktopFilterBar({
  values,
  livingAreas,
  onChange,
  onReset,
  sort,
  terms = true,
}: FilterBarProps) {
  const v = (k: FilterKey) => values[k] ?? '';
  const applied = MORE_FILTERS.filter((k) => !!values[k]).length;
  const [open, setOpen] = useState(applied > 0);
  // URL 이 바뀌어 숨은 필터에 값이 생기면 펼친다(닫혀 있으면 적용 중인 필터를 못 본다)
  useEffect(() => {
    if (applied > 0) setOpen(true);
  }, [applied]);
  const moreId = useId();
  const button =
    'min-h-10 rounded-[10px] border border-border-strong bg-surface px-3 py-1.5 text-sm font-semibold text-fg-2 hover:border-accent';
  return (
    <Card padding="sm" className="flex flex-col gap-2">
      <form
        role="search"
        aria-label={t('page.G2.filters')}
        className="flex flex-col gap-2"
        onSubmit={(e) => e.preventDefault()}
      >
        <div className="flex flex-wrap items-end gap-x-3 gap-y-2">
          <Field name="q" value={v('q')} onChange={onChange} wide />
          <PrimarySelects
            values={values}
            livingAreas={livingAreas}
            onChange={onChange}
            terms={terms}
          />
          <OpenNowChip values={values} onChange={onChange} />
          <Field
            name="resale_end_before"
            type="date"
            value={v('resale_end_before')}
            onChange={onChange}
          />
          {sort ? <SortSelect value={sort.value} onChange={sort.onChange} /> : null}
          <span className="ml-auto flex gap-2">
            <button
              type="button"
              aria-expanded={open}
              aria-controls={moreId}
              onClick={() => setOpen((x) => !x)}
              className={button}
            >
              {open ? (
                t('page.G2.filtersLess')
              ) : (
                <MetaText kind="count" k="page.G2.filtersMore" params={{ n: applied }} />
              )}
            </button>
            <button type="button" onClick={onReset} className={button}>
              {t('page.G2.clearFilters')}
            </button>
          </span>
        </div>
        {open ? (
          <div
            id={moreId}
            className="flex flex-wrap items-end gap-x-3 gap-y-2 border-t border-border pt-2"
          >
            <MoreFields values={values} onChange={onChange} terms={terms} />
          </div>
        ) : null}
      </form>
    </Card>
  );
}
