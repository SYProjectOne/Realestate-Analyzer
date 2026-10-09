import { createContext, useContext } from 'react';

/** 앱 전역 출처 패널 열기. ProvenanceProvider(앱 루트)가 값을 넣는다. */
export const ProvenanceContext = createContext<((prov: string) => void) | null>(null);

/** Provider 밖이면 null. FactCell은 prop → context 순으로 연다. */
export function useOpenProvenance(): ((prov: string) => void) | null {
  return useContext(ProvenanceContext);
}
