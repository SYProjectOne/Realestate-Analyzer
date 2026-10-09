/**
 * 차트 갤러리·단위 테스트 공용 데이터 — 계약 예시(contracts/examples/*.json, 인천·김포 보고서 기반)를 그대로 쓴다.
 * 특수 상태(미해결·대체 보정·표본 부족·미판정·질문 남김 …)는 예시를 복사해 필요한 필드만 바꾼다.
 * 지역명은 예시 데이터에만 있다(코드에는 없음).
 */
import compareExample from '../../../../contracts/examples/compare_b.json';
import elifExample from '../../../../contracts/examples/complex_detail_elif.json';
import kaiveExample from '../../../../contracts/examples/complex_detail_kaive.json';
import dashboardExample from '../../../../contracts/examples/dashboard_base.json';
import marketExample from '../../../../contracts/examples/market.json';
import provenanceConflictExample from '../../../../contracts/examples/provenance_conflict.json';
import provenanceScoreExample from '../../../../contracts/examples/provenance_score.json';
import sensitivityExample from '../../../../contracts/examples/sensitivity_base.json';
import type {
  CompareView,
  ComplexDetail,
  Dashboard,
  DecisionSet,
  Market,
  Provenance,
  ScoreRow,
  Sensitivity,
} from '@/lib/contract';

// JSON 모듈은 리터럴이 string으로 넓어져 계약 유니온 타입과 맞지 않는다 → 계약 타입으로 단언(예시는 계약 테스트가 스키마로 검증함)
const as = <T>(example: { value: unknown }): T => JSON.parse(JSON.stringify(example.value)) as T;

export const elif = (): ComplexDetail => as<ComplexDetail>(elifExample);
export const kaive = (): ComplexDetail => as<ComplexDetail>(kaiveExample);
export const market = (): Market => as<Market>(marketExample);
export const dashboard = (): Dashboard => as<Dashboard>(dashboardExample);
export const compare = (): CompareView => as<CompareView>(compareExample);
export const sensitivity = (): Sensitivity => as<Sensitivity>(sensitivityExample);
export const provenanceConflict = (): Provenance => as<Provenance>(provenanceConflictExample);
export const provenanceScore = (): Provenance => as<Provenance>(provenanceScoreExample);

/** 스냅샷 기준일(예시 공통) */
export const ASOF = '2026-10-08';

/** complex_id → 단지명 (C10 이름 표시용) — 대시보드 TOP 5 + 비교 행 */
export function complexNames(
  rows: ScoreRow[] = [...dashboard().top5, ...compare().rows],
): Record<string, string> {
  return Object.fromEntries(rows.map((row) => [String(row.complex_id), row.name]));
}

/** C06 특수: 한 단지의 성분 하나가 미판정(score null) */
export function rowsWithUnjudged(): ScoreRow[] {
  const rows = dashboard().top5.slice(0, 3);
  const target = rows[2];
  if (target?.components.liquidity) {
    target.components.liquidity = {
      ...target.components.liquidity,
      score: {
        v: null,
        label: '확인 불가',
        reason: '미판정',
        prov: null,
        checked_at: '2026-10-07',
        human: false,
      },
      raw: null,
      contribution: null,
    };
  }
  return rows;
}

/**
 * C07 정상: 계약 예시 base 결정 + 가상 후보 '모집공고 대기'(wait_new, 계약 2026-10-09.5 — complex_id null).
 * 재리뷰 F3 'C07 기준 이미지가 tie·wait_new 전' → 정상 상태 기준 이미지에 가상 후보가 보이게 한다(특수 = 동률).
 */
export function decisionWithWaitNew(): DecisionSet {
  const base = compare().decisions.base;
  if (!base) throw new Error('compare_b 예시에 base 결정이 없다');
  const first = base.items[0];
  if (!first) throw new Error('compare_b 예시 base 결정에 후보가 없다');
  return {
    ...base,
    items: [
      ...base.items,
      {
        ...first,
        option_key: 'wait_new',
        complex_id: null,
        label: '모집공고 대기',
        prob: { ...first.prob, v: 0.09 },
        chosen: false,
        tie: false,
        mismatch: false,
      },
    ],
  };
}

/** C07 특수: 판정기가 escape hatch로 질문을 남긴 decide 봉투 */
export function escapedDecision(): DecisionSet {
  const base = compare().decisions.base;
  if (!base) throw new Error('compare_b 예시에 base 결정이 없다');
  return {
    ...base,
    status: 'escaped',
    escaped: true,
    question: '자기자본 2억 기준 잔금대출 한도를 확인할 수 있습니까? <b>단지 A</b> & B',
  };
}

/** C10 특수: 모든 변형에서 TOP 5 변동 없음 */
export function stableSensitivity(): Sensitivity {
  const s = sensitivity();
  return {
    ...s,
    unstable: false,
    unstable_complex_ids: [],
    cells: s.cells.map((cell) => ({ ...cell, changed: false, entered: [], exited: [] })),
  };
}
