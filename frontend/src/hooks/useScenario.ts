import { useUrlParam } from './useUrlParam';

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
