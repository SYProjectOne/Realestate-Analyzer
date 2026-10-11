import { createContext, useContext, useEffect } from 'react';

/**
 * 출처 패널 열기(prov, 그 Fact 가 나온 리비전). 리비전을 생략하면(undefined) **연 순간** 보고 있던 리비전이다 —
 * 7차 M8·minor 17(D15-8): 서랍은 그 Fact 가 나온 리비전으로 조회하고, 연 뒤 화면 리비전이 바뀌어도 따라가지 않는다.
 */
export type OpenProvenance = (prov: string, snapshotId?: string | null) => void;

/** 앱 전역 출처 패널 열기. ProvenanceProvider(앱 루트)가 값을 넣는다. */
export const ProvenanceContext = createContext<OpenProvenance | null>(null);

/**
 * 출처 패널이 조회할 리비전(계약 .11 F1 `GET /provenance/{id}?snapshot_id=`) 설정. 패널은 라우터 바깥(앱 루트)에 있어
 * URL 을 읽지 못하므로 AppLayout 이 지금 보고 있는 리비전을 알려 준다(`useProvenanceSnapshot`).
 */
export const ProvenanceSnapshotContext = createContext<
  ((snapshotId: string | null) => void) | null
>(null);

/** Provider 밖이면 null. FactCell은 prop → context 순으로 연다. */
export function useOpenProvenance(): OpenProvenance | null {
  return useContext(ProvenanceContext);
}

/** 지금 보고 있는 리비전을 출처 패널에 알린다(AppLayout 이 한 번 부른다) */
export function useProvenanceSnapshot(snapshotId: string | null): void {
  const set = useContext(ProvenanceSnapshotContext);
  useEffect(() => {
    set?.(snapshotId);
  }, [set, snapshotId]);
}
