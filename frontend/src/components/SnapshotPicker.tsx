import { useId } from 'react';
import type { Snapshot } from '@/api/types';
import { t } from '@/i18n';
import { formatDate } from '@/lib/format';

export interface SnapshotPickerProps {
  /** 기준일 목록 (GET /regions/{id}/snapshots), 최신이 앞 */
  snapshots: Snapshot[];
  /** 선택 snapshot id (URL ?snapshot=). null이면 첫 항목 */
  value: string | null;
  onChange: (snapshotId: string) => void;
  disabled?: boolean;
  /** 라벨 문구 (기본 t('header.snapshot')). G8 SnapshotPairPicker가 두 개를 쓸 때 바꾼다 */
  label?: string;
}

/** 기준일 선택 select. 상태(building 등)는 옵션 텍스트에 함께. */
export function SnapshotPicker({
  snapshots,
  value,
  onChange,
  disabled = false,
  label,
}: SnapshotPickerProps) {
  const id = useId();
  const selected = value ?? snapshots[0]?.id ?? '';
  return (
    <span className="inline-flex items-center gap-1.5 text-sm">
      <label htmlFor={id} className="text-muted">
        {label ?? t('header.snapshot')}
      </label>
      <select
        id={id}
        value={selected}
        disabled={disabled || snapshots.length === 0}
        onChange={(event) => onChange(event.target.value)}
        className="rounded border border-border bg-surface px-2 py-1 text-fg"
      >
        {snapshots.length === 0 ? <option value="">{t('header.snapshotNone')}</option> : null}
        {snapshots.map((snapshot) => (
          <option key={snapshot.id} value={snapshot.id}>
            {formatDate(snapshot.asof_date)}
          </option>
        ))}
      </select>
    </span>
  );
}
