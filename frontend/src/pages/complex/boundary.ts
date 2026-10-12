import { t } from '@/i18n';

/**
 * 계약 .16 F5(D21-6) G3 '범위 경계' 사유. API 는 범위 사유 문자열을 내지 않으므로(보고서·파이프라인만 `ScopeResult.reason`)
 * 서버 `analysis.scope.judge_scope` 첫 행과 같은 규칙을 단지 머리 값(inclusion_class·address·legal_dong_code)으로 다시 쓴다:
 * 법정동이 없고 주소에 동·읍·면·리·N가 이름이 없으면 '범위 경계(주소에 동 없음)', 그 밖은 '…(주소가 지역 법정동에 매칭 안 됨)'.
 * 주소 모양 검사는 서버 `has_dong_name` 과 같은 정규식(파싱 — 판단 아님, AGENTS 규칙 3).
 * 계약 변경 요청(보고): 화면이 규칙을 복제하지 않도록 상세 머리에 범위 사유 문자열을 내 달라.
 */
const DONG_TOKEN_RE = /[가-힣][가-힣0-9]*(?:동|읍|면|리|[0-9]가)$/;
const ADDR_SPLIT_RE = /[\s(),[\]/·]+/;

const BOUNDARY_CLASS = '범위 경계';

/** 주소 토큰 중 법정동 이름 모양이 있는가(서버 `analysis.scope.has_dong_name`) */
export function hasDongName(address: string): boolean {
  return address.split(ADDR_SPLIT_RE).some((token) => token !== '' && DONG_TOKEN_RE.test(token));
}

/** 포함 분류가 '범위 경계'면 그 사유 문구, 아니면 null */
export function boundaryReason(
  inclusionClass: string,
  address: string | null | undefined,
  legalDongCode: string | null | undefined,
): string | null {
  if (inclusionClass !== BOUNDARY_CLASS) return null;
  if (!legalDongCode && address && !hasDongName(address)) {
    return t('page.G3.header.boundary.noDong');
  }
  return t('page.G3.header.boundary.unmatched');
}
