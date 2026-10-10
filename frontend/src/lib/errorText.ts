import { ApiError, isMaterializePending } from '@/api/client';
import { t } from '@/i18n';

/**
 * 조회 오류 문구(계약 .11 F12): materialize_pending = 아직 준비 중(자동 재시도가 끝난 뒤), stored_view_mismatch =
 * 서버 오류(발행 저장본 검증 실패 — 관리자 확인), 그 밖 = 일반 '불러오지 못했습니다'.
 */
export function queryErrorText(error: Error): string {
  return specialErrorText(error) ?? t('page.common.loadError', { detail: error.message });
}

/** 계약 .11 새 오류 code 의 화면 문구(준비 중·저장본 검증 실패). 그 밖이면 null — 호출 측 문구를 쓴다 */
export function specialErrorText(error: unknown): string | null {
  if (isMaterializePending(error)) return t('page.common.materializePendingStill');
  if (error instanceof ApiError && error.code === 'stored_view_mismatch') {
    return t('page.common.storedViewMismatch', { detail: error.detail });
  }
  return null;
}
