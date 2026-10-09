import type { TKey } from '@/i18n';
import { metaNumber, metaText, type MetaFormat, type MetaParam } from '@/lib/meta';

/**
 * 비수치 메타의 종류 — 화면에 보이는 숫자 중 사실(Fact)이 아닌 것. `data-meta` 로 DOM 에 남아
 * e2e·리뷰가 "라벨 없는 숫자 = 사실 아님" 을 확인할 수 있다.
 *  - count: 목록·선택·표본 개수   - rank: 저장된 순위(점수 run 결과의 순번)
 *  - duration: 소요 시간          - status: HTTP 상태 코드
 *  - seq: 판정 로그·납부 회차 같은 번호   - input: 사용자가 입력 중인 값(가중치 등)
 *  - progress: 잡 진행률           - size: 파일 크기
 *  - derived: 차트 표의 파생값(그 차트의 사실은 Fact 셀이 따로 보인다)
 *  - confidence: 판정기 자기 평가(사실 아님 — 판정 봉투 메타)
 */
export type MetaKind =
  | 'count'
  | 'rank'
  | 'duration'
  | 'status'
  | 'seq'
  | 'input'
  | 'progress'
  | 'size'
  | 'derived'
  | 'confidence';

export interface MetaValueProps {
  kind: MetaKind;
  value: number;
  /** 포맷(기본: 정수 → 천 단위, 소수 → 둘째 자리) */
  as?: MetaFormat;
  digits?: number;
  className?: string;
}

/** 사실이 아닌 숫자 하나 — FactCell 과 달리 라벨·출처가 없다는 것을 명시한다 */
export function MetaValue({ kind, value, as, digits, className = '' }: MetaValueProps) {
  const text =
    as === undefined && digits === undefined
      ? metaNumber(value)
      : metaNumber({ n: value, as, digits });
  return (
    <span data-meta={kind} className={`tabular-nums ${className}`}>
      {text}
    </span>
  );
}

export interface MetaTextProps {
  kind: MetaKind;
  /** ko.json 키 */
  k: TKey;
  params: Record<string, MetaParam>;
  className?: string;
}

/** 메타 숫자가 들어간 문구("3개 선택", "128ms") — `metaText` 의 JSX 판 */
export function MetaText({ kind, k, params, className }: MetaTextProps) {
  const text = metaText(k, params);
  return (
    <span data-meta={kind} className={className}>
      {text}
    </span>
  );
}
