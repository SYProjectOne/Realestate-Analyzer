import { useId } from 'react';
import { t } from '@/i18n';
import type { RegionLike } from '@/lib/contract';

export const ADD_REGION_VALUE = '__add_region__';

export interface RegionPickerProps {
  /** GET /regions (계약 Region·임시 Region 모두 — id·name만 쓴다) */
  regions: readonly RegionLike[];
  /** 선택 region id (URL ?region=). null이면 첫 항목. 숫자 id도 받는다 */
  value: string | number | null;
  onChange: (regionId: string) => void;
  /** "지역 추가" 항목 선택 → 보통 navigate('/regions/new') (D2-5) */
  onAddRegion: () => void;
  disabled?: boolean;
}

/** 지역 선택 select + 맨 끝 "+ 지역 추가" 항목. 지역명은 서버 값만 쓴다(하드코딩 금지). */
export function RegionPicker({
  regions,
  value,
  onChange,
  onAddRegion,
  disabled = false,
}: RegionPickerProps) {
  const id = useId();
  const selected = String(value ?? regions[0]?.id ?? '');
  return (
    <span className="inline-flex items-center gap-1.5 text-sm">
      <label htmlFor={id} className="text-muted">
        {t('header.region')}
      </label>
      <select
        id={id}
        value={selected}
        disabled={disabled}
        onChange={(event) => {
          if (event.target.value === ADD_REGION_VALUE) onAddRegion();
          else onChange(event.target.value);
        }}
        className="rounded-sm border border-border bg-surface px-2 py-1 text-fg"
      >
        {regions.length === 0 ? <option value="">{t('header.regionNone')}</option> : null}
        {regions.map((region) => (
          <option key={region.id} value={region.id}>
            {region.name}
          </option>
        ))}
        <option value={ADD_REGION_VALUE}>{t('header.regionAdd')}</option>
      </select>
    </span>
  );
}
