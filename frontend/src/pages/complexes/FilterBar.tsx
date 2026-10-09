import { useId } from 'react';
import { INTAKE_STATUSES, JUDGE_SCOPES, type LivingArea } from '@/api/types';
import { t, type TKey } from '@/i18n';
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

/** G2 FilterBar — 생활권·접수·택지·전매 종료일·가격대·입주연도·포함 분류(+판정 범위·단지명). 값은 URL 쿼리 */
export function FilterBar({ values, livingAreas, onChange, onReset }: FilterBarProps) {
  const v = (k: FilterKey) => values[k] ?? '';
  return (
    <form
      role="search"
      aria-label={t('page.G2.filters')}
      className="flex flex-wrap items-end gap-3 rounded-sm border border-border bg-surface p-3"
      onSubmit={(e) => e.preventDefault()}
    >
      <Field name="q" value={v('q')} onChange={onChange} />
      <Field
        name="living_area"
        value={v('living_area')}
        onChange={onChange}
        options={livingAreas.map((la) => ({ value: la.id, label: la.name }))}
      />
      <Field
        name="intake_status"
        value={v('intake_status')}
        onChange={onChange}
        options={INTAKE_STATUSES.map((s) => ({ value: s, label: enumText('intake.status', s) }))}
      />
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
        options={INCLUSION.map((s) => ({ value: s, label: enumText('page.common.inclusion', s) }))}
      />
      <Field
        name="judge_scope"
        value={v('judge_scope')}
        onChange={onChange}
        options={SCOPES.map((s) => ({ value: s, label: enumText('page.common.judgeScope', s) }))}
      />
      <button
        type="button"
        onClick={onReset}
        className="rounded-sm border border-border px-2 py-1 text-sm"
      >
        {t('page.G2.clearFilters')}
      </button>
    </form>
  );
}
