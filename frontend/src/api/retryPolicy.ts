/**
 * 쿼리 재시도 규칙(운영·테스트 QueryClient 공통).
 *
 * 계약 .11(D14-9, F12·F15): 발행 리비전 저장본을 worker 가 아직 만들지 않았으면 읽기 GET 이 503
 * `materialize_pending` + `Retry-After`(초)다. 화면은 '준비 중'을 보이고(`QueryState` 가 failureReason 으로)
 * Retry-After 뒤 자동으로 다시 부른다 — 그 밖의 오류는 `base` 번만 다시 부른다(운영 1, 테스트 0).
 */
import { isMaterializePending } from './client';

/** materialize_pending 자동 재시도 상한(기본 간격 3초 × 40 ≈ 2분 — 그 뒤엔 '준비 중' + 다시 시도 버튼) */
export const MATERIALIZE_RETRY_MAX = 40;
/** Retry-After 가 없을 때의 간격 */
export const MATERIALIZE_RETRY_DEFAULT_MS = 3000;
const MATERIALIZE_RETRY_MIN_MS = 500;
const MATERIALIZE_RETRY_MAX_MS = 30_000;

export function queryRetry(base: number): (failureCount: number, error: unknown) => boolean {
  return (failureCount, error) =>
    isMaterializePending(error) ? failureCount < MATERIALIZE_RETRY_MAX : failureCount < base;
}

export function queryRetryDelay(failureCount: number, error: unknown): number {
  if (isMaterializePending(error)) {
    const ms = error.retryAfterMs ?? MATERIALIZE_RETRY_DEFAULT_MS;
    return Math.min(Math.max(ms, MATERIALIZE_RETRY_MIN_MS), MATERIALIZE_RETRY_MAX_MS);
  }
  // TanStack 기본과 같다
  return Math.min(1000 * 2 ** failureCount, 30_000);
}
