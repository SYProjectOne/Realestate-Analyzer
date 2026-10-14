/**
 * 일정(체크리스트·캘린더) 표시 도우미 — R9-UI P2(G1 다가오는 일정)·사용자 피드백(G7 캘린더 '만료' 배지).
 * 판단이 아니라 표시 문구 고르기다: 종류 enum → 쉬운 말, 서버 제목의 '전매제한' 표식이면 '전매 가능 시작'.
 */
import type { ChecklistItem } from '@/api/types';
import { t, tDynamic } from '@/i18n';
import { kstDay } from '@/lib/format';

/** 서버 체크리스트 제목 표식(normalize/checklist.py '전매제한 종료(당첨자 발표일 + N개월, 산술)') */
const RESALE_MARKER = '전매제한';

/** 전매제한 종료 항목인가(종류 '만료' + 제목 표식) — '만료'는 토지거래허가구역 지정 만료 등에도 쓰인다 */
export function isResaleEnd(item: Pick<ChecklistItem, 'kind' | 'title'>): boolean {
  return item.kind === '만료' && item.title.includes(RESALE_MARKER);
}

/** 종류 글자(쉬운 말). 전매제한 종료는 '전매 가능 시작'(나쁜 일이 끝나는 것처럼 읽히는 '만료' 대신) */
export function scheduleKindText(item: Pick<ChecklistItem, 'kind' | 'title'>): string {
  if (isResaleEnd(item)) return t('page.common.scheduleKind.resaleOpen');
  return tDynamic(`page.common.scheduleKind.${item.kind}`, item.kind);
}

/** 제목 괄호 안 계산 근거('당첨자 발표일 + 12개월, 산술') — 전매제한 종료 항목만, 없으면 null */
export function scheduleBasis(item: Pick<ChecklistItem, 'kind' | 'title'>): string | null {
  if (!isResaleEnd(item)) return null;
  const match = /\(([^()]+)\)\s*$/.exec(item.title);
  return match?.[1] ?? null;
}

function dayNumber(iso: string): number | null {
  const day = kstDay(iso);
  if (!day) return null;
  const [y, m, d] = day.split('-').map(Number);
  if (y === undefined || m === undefined || d === undefined) return null;
  return Date.UTC(y, m - 1, d) / 86_400_000;
}

/** 날짜가 기준일 ~ 기준일 + days 안인가(표시 범위 고르기 — 계산값을 만들지 않는다) */
export function withinDays(date: string, asof: string, days: number): boolean {
  const a = dayNumber(date);
  const b = dayNumber(asof);
  if (a === null || b === null) return false;
  return a >= b && a - b <= days;
}
