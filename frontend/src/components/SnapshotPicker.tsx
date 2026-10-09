import { useId } from 'react';
import { t } from '@/i18n';
import type { SnapshotLike } from '@/lib/contract';
import { formatDate } from '@/lib/format';

export interface SnapshotPickerProps {
  /** 기준일 목록 (GET /regions/{id}/snapshots), 최신이 앞 */
  snapshots: readonly SnapshotLike[];
  /** 선택 snapshot id (URL ?snapshot=). null이면 첫 항목. 숫자 id도 받는다 */
  value: string | number | null;
  onChange: (snapshotId: string) => void;
  disabled?: boolean;
  /** 라벨 문구 (기본 t('header.snapshot')). G8 SnapshotPairPicker가 두 개를 쓸 때 바꾼다 */
  label?: string;
}

/** 옵션 문구: 기준일 + (일부 수집 실패 / 생성 중) */
export function snapshotText(snapshot: SnapshotLike): string {
  const date = formatDate(snapshot.asof_date);
  if (snapshot.degraded) return t('picker.snapshotDegraded', { date });
  if (snapshot.status === 'building') return t('picker.snapshotBuilding', { date });
  return date;
}

/** 기준일 선택 select. 상태(degraded·building)는 옵션 텍스트에 함께. */
export function SnapshotPicker({
  snapshots,
  value,
  onChange,
  disabled = false,
  label,
}: SnapshotPickerProps) {
  const id = useId();
  const selected = String(value ?? snapshots[0]?.id ?? '');
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
            {snapshotText(snapshot)}
          </option>
        ))}
      </select>
    </span>
  );
}
