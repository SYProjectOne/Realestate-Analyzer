import { createContext, useContext, useEffect } from 'react';

/** 앱 전역 출처 패널 열기. ProvenanceProvider(앱 루트)가 값을 넣는다. */
export const ProvenanceContext = createContext<((prov: string) => void) | null>(null);

/**
 * 출처 패널이 조회할 리비전(계약 .11 F1 `GET /provenance/{id}?snapshot_id=`) 설정. 패널은 라우터 바깥(앱 루트)에 있어
 * URL 을 읽지 못하므로 AppLayout 이 지금 보고 있는 리비전을 알려 준다(`useProvenanceSnapshot`).
 */
export const ProvenanceSnapshotContext = createContext<
  ((snapshotId: string | null) => void) | null
>(null);

/** Provider 밖이면 null. FactCell은 prop → context 순으로 연다. */
export function useOpenProvenance(): ((prov: string) => void) | null {
  return useContext(ProvenanceContext);
}

/** 지금 보고 있는 리비전을 출처 패널에 알린다(AppLayout 이 한 번 부른다) */
export function useProvenanceSnapshot(snapshotId: string | null): void {
  const set = useContext(ProvenanceSnapshotContext);
  useEffect(() => {
    set?.(snapshotId);
  }, [set, snapshotId]);
}
