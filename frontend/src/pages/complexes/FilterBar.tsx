import { useEffect, useId, useState } from 'react';
import { INTAKE_STATUSES, JUDGE_SCOPES, type LivingArea } from '@/api/types';
import { t, type TKey } from '@/i18n';
import { MetaText } from '@/components';
import { enumText } from '../_shared';
import type { FilterKey, FilterValues } from './params';

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

const inputClass = 'rounded-sm border border-border bg-surface px-2 py-1 text-sm text-fg';

function Field({
  name,
  value,
  onChange,
  options,
  type = 'text',
  inputMode,
  placeholder,
}: {
  name: FilterKey;
  value: string;
  onChange: (key: FilterKey, value: string) => void;
  options?: Option[];
  type?: 'text' | 'date' | 'number';
  inputMode?: 'decimal' | 'numeric';
  placeholder?: string;
}) {
  const id = useId();
  const label = t(`page.G2.filter.${name}` as TKey);
  return (
    <span className="flex flex-col gap-0.5 text-xs">
      <label htmlFor={id} className="text-muted">
        {label}
      </label>
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
          placeholder={placeholder}
          step={type === 'number' ? 'any' : undefined}
          onChange={(e) => onChange(name, e.target.value)}
          className={`${inputClass} w-32`}
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
}

/** R9-UI P4: 늘 보이는 핵심 필터(단지명·접수·생활권) */
export const PRIMARY_FILTERS = ['q', 'intake_status', 'living_area'] as const;
/** '필터 더 보기'(1클릭) 안의 필터 7칸 — 값이 있으면 자동으로 펼친다 */
export const MORE_FILTERS = [
  'land_type',
  'resale_end_before',
  'price_min',
  'price_max',
  'move_in_year',
  'inclusion_class',
  'judge_scope',
] as const satisfies readonly FilterKey[];

/** 지금 접수 가능 칩이 거는 값(계약 IntakeStatus) */
const OPEN_NOW = '가능';

/**
 * G2 FilterBar — 핵심 3칸 + '필터 더 보기'(택지·전매 종료일·가격대·입주연도·단지 분류·점수 계산 범위) + '지금 접수 가능만' 칩.
 * 값은 URL 쿼리. 접어도 적용 중인 필터 개수가 버튼에 보이고, 숨은 필터에 값이 있으면 펼친 채로 연다(30-proposal §5-4).
 */
export function FilterBar({ values, livingAreas, onChange, onReset }: FilterBarProps) {
  const v = (k: FilterKey) => values[k] ?? '';
  const applied = MORE_FILTERS.filter((k) => !!values[k]).length;
  const [open, setOpen] = useState(applied > 0);
  // URL 이 바뀌어 숨은 필터에 값이 생기면 펼친다(닫혀 있으면 적용 중인 필터를 못 본다)
  useEffect(() => {
    if (applied > 0) setOpen(true);
  }, [applied]);
  const moreId = useId();
  const openNow = values.intake_status === OPEN_NOW;
  return (
    <form
      role="search"
      aria-label={t('page.G2.filters')}
      className="flex flex-col gap-2 rounded-sm border border-border bg-surface p-3"
      onSubmit={(e) => e.preventDefault()}
    >
      <div className="flex flex-wrap items-end gap-3">
        <Field name="q" value={v('q')} onChange={onChange} />
        <Field
          name="intake_status"
          value={v('intake_status')}
          onChange={onChange}
          options={INTAKE_STATUSES.map((s) => ({ value: s, label: enumText('intake.status', s) }))}
        />
        <Field
          name="living_area"
          value={v('living_area')}
          onChange={onChange}
          options={livingAreas.map((la) => ({ value: la.id, label: la.name }))}
        />
        <button
          type="button"
          aria-pressed={openNow}
          onClick={() => onChange('intake_status', openNow ? '' : OPEN_NOW)}
          className={`rounded-full border px-3 py-1 text-sm ${
            openNow ? 'border-accent bg-accent text-accent-fg' : 'border-border'
          }`}
        >
          {openNow ? t('page.G2.openNowChipOff') : t('page.G2.openNowChip')}
        </button>
        <button
          type="button"
          aria-expanded={open}
          aria-controls={moreId}
          onClick={() => setOpen((x) => !x)}
          className="rounded-sm border border-border px-2 py-1 text-sm"
        >
          {open ? (
            t('page.G2.filtersLess')
          ) : (
            <MetaText kind="count" k="page.G2.filtersMore" params={{ n: applied }} />
          )}
        </button>
        <button
          type="button"
          onClick={onReset}
          className="rounded-sm border border-border px-2 py-1 text-sm"
        >
          {t('page.G2.clearFilters')}
        </button>
      </div>
      {open ? (
        <div id={moreId} className="flex flex-wrap items-end gap-3 border-t border-border pt-2">
          <Field
            name="land_type"
            value={v('land_type')}
            onChange={onChange}
            options={LAND_TYPES.map((s) => ({ value: s, label: enumText('page.G2.landType', s) }))}
          />
          <Field
            name="resale_end_before"
            type="date"
            value={v('resale_end_before')}
            onChange={onChange}
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
            options={INCLUSION.map((s) => ({
              value: s,
              label: enumText('page.common.inclusion', s),
            }))}
          />
          <Field
            name="judge_scope"
            value={v('judge_scope')}
            onChange={onChange}
            options={SCOPES.map((s) => ({
              value: s,
              label: enumText('page.common.judgeScope', s),
            }))}
          />
        </div>
      ) : null}
    </form>
  );
}
