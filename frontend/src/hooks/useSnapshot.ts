import { useSnapshots } from '@/api/hooks';
import type { Snapshot } from '@/api/types';
import { SNAPSHOT_PARAM } from './snapshotParam';
import { useActiveRegion } from './useActiveRegion';
import { useUrlParam } from './useUrlParam';

export { SNAPSHOT_PARAM };

export interface SnapshotState {
  /** 실제로 쓸 snapshot id(URL 문자열): `?snapshot=` → 지역 latest_snapshot.id → 목록 첫 항목. 없으면 null */
  snapshotId: string | null;
  /** URL에 명시된 값만 (기본값 적용 전) */
  explicitSnapshotId: string | null;
  snapshot: Snapshot | null;
  snapshots: Snapshot[];
  isLoading: boolean;
  setSnapshot: (id: string | null) => void;
}

/** 기준일 전역 공유(RA §7): `?snapshot=`. 화면은 snapshotId만 쓰면 된다. */
export function useSnapshot(): SnapshotState {
  const [explicitSnapshotId, set] = useUrlParam(SNAPSHOT_PARAM);
  const { region, isLoading: regionLoading } = useActiveRegion();
  const { data: snapshots = [], isLoading: snapshotsLoading } = useSnapshots(region?.id);
  const fallback = region?.latest_snapshot?.id ?? snapshots[0]?.id ?? null;
  const snapshotId = explicitSnapshotId ?? (fallback === null ? null : String(fallback));
  const snapshot =
    snapshots.find((s) => String(s.id) === snapshotId) ??
    (region?.latest_snapshot && String(region.latest_snapshot.id) === snapshotId
      ? region.latest_snapshot
      : null);
  return {
    snapshotId,
    explicitSnapshotId,
    snapshot,
    snapshots,
    isLoading: regionLoading || snapshotsLoading,
    setSnapshot: (id) => set(id),
  };
}
