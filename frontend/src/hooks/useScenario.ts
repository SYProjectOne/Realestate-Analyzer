import type { Scenario } from '@/api/types';
import { useUrlParam } from './useUrlParam';

/** URL·API 쿼리용 시나리오 키: 내장은 code(base|A|B|C|D), 사용자 시나리오는 id 문자열(계약 Scenario 파라미터) */
export function scenarioKey(s: Pick<Scenario, 'id' | 'code'>): string {
  return s.code ?? String(s.id);
}

export const SCENARIO_PARAM = 'scenario';

export interface ScenarioState {
  /** URL `?scenario=` 값. null이면 서버 기본 시나리오 */
  scenarioId: string | null;
  setScenario: (id: string | null) => void;
}

/** 상황 토글 전역 공유(RA §7): 모든 화면이 같은 `?scenario=`를 읽고 쓴다. */
export function useScenario(): ScenarioState {
  const [scenarioId, set] = useUrlParam(SCENARIO_PARAM);
  return { scenarioId, setScenario: (id) => set(id) };
}
