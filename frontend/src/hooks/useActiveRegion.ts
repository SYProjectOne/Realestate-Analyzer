import { useRegions } from '@/api/hooks';
import type { Region } from '@/api/types';
import { SNAPSHOT_PARAM } from './snapshotParam';
import { useUrlParam } from './useUrlParam';

export const REGION_PARAM = 'region';

export interface ActiveRegionState {
  /** `?region=` → 목록 첫 항목. 지역이 없거나 로딩 중이면 null */
  region: Region | null;
  regions: Region[];
  isLoading: boolean;
  /** 로딩이 끝났고 지역이 0개 → G1은 /regions/new로 보낸다 */
  isEmpty: boolean;
  /** 지역을 바꾸면 ?snapshot=은 지운다(다른 지역의 스냅샷이므로) */
  setRegion: (id: string) => void;
}

export function useActiveRegion(): ActiveRegionState {
  const [regionParam, set] = useUrlParam(REGION_PARAM);
  const { data: regions = [], isLoading, isSuccess } = useRegions();
  const region = regions.find((r) => String(r.id) === regionParam) ?? regions[0] ?? null;
  return {
    region,
    regions,
    isLoading,
    isEmpty: isSuccess && regions.length === 0,
    setRegion: (id) => set(id, { drop: [SNAPSHOT_PARAM] }),
  };
}
