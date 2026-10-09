import { useId } from 'react';
import { t } from '@/i18n';
import type { SnapshotLike } from '@/lib/contract';
import { formatDate } from '@/lib/format';
import { metaText } from '@/lib/meta';

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

/** 리비전 번호(없으면 1 — 계약 .7 응답) */
export const revisionOf = (snapshot: SnapshotLike): number => snapshot.revision ?? 1;

/**
 * 옵션 문구: 기준일(+ 리비전 2 이상이면 "· 리비전 n", D11-1) + (일부 수집 실패 / 생성 중).
 * 리비전 번호는 사실이 아닌 버전 번호(비수치 메타)다.
 */
export function snapshotText(snapshot: SnapshotLike): string {
  const day = formatDate(snapshot.asof_date);
  const rev = revisionOf(snapshot);
  const date = rev > 1 ? metaText('picker.revision', { date: day, n: rev }) : day;
  if (snapshot.degraded) return t('picker.snapshotDegraded', { date });
  if (snapshot.status === 'building') return t('picker.snapshotBuilding', { date });
  return date;
}

/** 옵션 툴팁: 리비전 사유(리비전 2 이상) */
export function snapshotTitle(snapshot: SnapshotLike): string | undefined {
  const rev = revisionOf(snapshot);
  if (rev <= 1 || !snapshot.revision_reason) return undefined;
  return metaText('picker.revisionReason', { n: rev, reason: snapshot.revision_reason });
}

/**
 * 기본 스냅샷(D11-1 "화면 기본 = 최신 published 리비전"): 기준일 최신 → 같은 기준일 안에서 리비전 최신 순,
 * published 가 있으면 그중 첫째, 없으면 목록 첫째.
 */
export function defaultSnapshot<T extends SnapshotLike>(snapshots: readonly T[]): T | null {
  const ordered = [...snapshots].sort(
    (a, b) => b.asof_date.localeCompare(a.asof_date) || revisionOf(b) - revisionOf(a),
  );
  return ordered.find((s) => s.status === 'published') ?? ordered[0] ?? null;
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
        className="rounded-sm border border-border bg-surface px-2 py-1 text-fg"
      >
        {snapshots.length === 0 ? <option value="">{t('header.snapshotNone')}</option> : null}
        {snapshots.map((snapshot) => (
          <option key={snapshot.id} value={snapshot.id} title={snapshotTitle(snapshot)}>
            {snapshotText(snapshot)}
          </option>
        ))}
      </select>
    </span>
  );
}
