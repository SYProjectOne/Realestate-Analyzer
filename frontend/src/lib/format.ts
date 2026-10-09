/**
 * 숫자·날짜 포맷 — 화면에서 숫자를 문자열로 바꾸는 유일한 곳 (AGENTS 규칙 12, RA §7).
 * 컴포넌트는 FactCell을 쓰고, 차트 축·툴팁·표 셀은 여기 함수를 쓴다.
 * 단위 문자열(억·만·원·㎡·세대·D-day)도 ko.json에서 온다.
 */
import type { Fact, IsoDate } from '@/api/types';
import { t } from '@/i18n';

/** FactCell·DataTableToggle 열의 단위. */
export type FactUnit =
  /** 원 정수 → "7억 4,900만원" */
  | 'won'
  /** 원 정수 → "7.49억" (좁은 칸·차트) */
  | 'eok'
  /** 이미 % 값 → "12.3%" */
  | 'pct'
  /** 0~1 확률 → "48%" */
  | 'prob'
  /** ㎡ → "84.97㎡" */
  | 'm2'
  /** ISO 날짜 → "2026-10-11 (D-3)" (asof가 있을 때) */
  | 'date'
  /** YYYY-MM → "2028-03" */
  | 'ym'
  /** 0~10 점수 → "7.26" */
  | 'score'
  /** 세대 수 → "1,234세대" */
  | 'households'
  /** 건수·개수 → "1,234" */
  | 'count'
  /** 경쟁률 → "12.3:1" */
  | 'ratio'
  /** 순위 → "1위" */
  | 'rank'
  /** 천 단위 구분만 */
  | 'number'
  /** 문자열 그대로 */
  | 'text';

export interface FormatOptions {
  /** 기준일(D± 계산). 보통 스냅샷 asof_date */
  asof?: IsoDate | null;
  /** 소수 자릿수 덮어쓰기 */
  digits?: number;
}

const nf = (digits = 0) =>
  new Intl.NumberFormat('ko-KR', { minimumFractionDigits: digits, maximumFractionDigits: digits });

const unknown = () => t('empty.unknown');

export function formatNumber(n: number, digits = 0): string {
  if (!Number.isFinite(n)) return unknown();
  return nf(digits).format(n);
}

/** 원 → "7억 4,900만원". 만 단위에서 반올림한다. 1만 미만은 원 단위 그대로. */
export function formatWon(won: number): string {
  if (!Number.isFinite(won)) return unknown();
  const sign = won < 0 ? '-' : '';
  const abs = Math.abs(won);
  const wonSuffix = t('unit.won');
  if (abs < 10_000) return `${sign}${nf().format(Math.round(abs))}${wonSuffix}`;
  const totalMan = Math.round(abs / 10_000);
  const eok = Math.floor(totalMan / 10_000);
  const man = totalMan % 10_000;
  const parts: string[] = [];
  if (eok > 0) parts.push(`${nf().format(eok)}${t('unit.eok')}`);
  if (man > 0) parts.push(`${nf().format(man)}${t('unit.man')}`);
  return `${sign}${parts.join(' ')}${wonSuffix}`;
}

/** 원 → "7.49억" (차트 축·좁은 칸) */
export function formatEok(won: number, digits = 2): string {
  if (!Number.isFinite(won)) return unknown();
  return `${(won / 100_000_000).toFixed(digits)}${t('unit.eok')}`;
}

/** 이미 퍼센트인 값 → "12.3%" */
export function formatPercent(pct: number, digits = 1): string {
  if (!Number.isFinite(pct)) return unknown();
  return `${pct.toFixed(digits)}${t('unit.percent')}`;
}

/** 0~1 확률 → "48%" */
export function formatProb(p: number, digits = 0): string {
  if (!Number.isFinite(p)) return unknown();
  return `${(p * 100).toFixed(digits)}${t('unit.percent')}`;
}

export function formatArea(m2: number, digits = 2): string {
  if (!Number.isFinite(m2)) return unknown();
  return `${m2.toFixed(digits)}${t('unit.m2')}`;
}

export function formatScore(score: number, digits = 2): string {
  if (!Number.isFinite(score)) return unknown();
  return score.toFixed(digits);
}

export function formatCount(n: number, kind: 'households' | 'count' | null = null): string {
  if (!Number.isFinite(n)) return unknown();
  const base = nf().format(Math.round(n));
  if (kind === 'households') return `${base}${t('unit.households')}`;
  if (kind === 'count') return `${base}${t('unit.count')}`;
  return base;
}

export function formatRank(rank: number): string {
  if (!Number.isFinite(rank)) return unknown();
  return t('unit.rank', { rank: Math.round(rank) });
}

export function formatRatio(ratio: number, digits = 1): string {
  if (!Number.isFinite(ratio)) return unknown();
  return t('unit.ratio', { ratio: ratio.toFixed(digits) });
}

/** ISO 날짜/일시의 날짜 부분 → UTC 기준 일수 (시간대 영향 없음) */
function toDayNumber(iso: string): number | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!match) return null;
  const [, y, m, d] = match;
  return Date.UTC(Number(y), Number(m) - 1, Number(d)) / 86_400_000;
}

/** 기준일 대비 D±: 미래 → "D-3", 과거 → "D+3", 같은 날 → "D-day" */
export function formatDday(date: string, asof: string): string {
  const a = toDayNumber(date);
  const b = toDayNumber(asof);
  if (a === null || b === null) return unknown();
  const diff = a - b;
  if (diff === 0) return t('unit.dday');
  return diff > 0 ? t('unit.dminus', { n: diff }) : t('unit.dplus', { n: -diff });
}

/** "2026-10-11" 또는 기준일이 있으면 "2026-10-11 (D-3)" */
export function formatDate(date: string, asof?: string | null): string {
  const day = /^\d{4}-\d{2}-\d{2}/.exec(date)?.[0];
  if (!day) return date;
  return asof ? `${day} (${formatDday(day, asof)})` : day;
}

/** "2028-03" → "2028년 상반기" (C1 부제: 명제 시점) */
export function formatHalfYear(ym: string): string {
  const match = /^(\d{4})-(\d{2})/.exec(ym);
  if (!match) return ym;
  const year = match[1] ?? '';
  const month = Number(match[2]);
  return month <= 6 ? t('unit.half1', { year }) : t('unit.half2', { year });
}

/** 단위별 숫자 포맷 (DataTableToggle·차트 툴팁 공용) */
export function formatValue(value: number, unit: FactUnit, options: FormatOptions = {}): string {
  const { digits } = options;
  switch (unit) {
    case 'won':
      return formatWon(value);
    case 'eok':
      return formatEok(value, digits);
    case 'pct':
      return formatPercent(value, digits);
    case 'prob':
      return formatProb(value, digits);
    case 'm2':
      return formatArea(value, digits);
    case 'score':
      return formatScore(value, digits);
    case 'households':
      return formatCount(value, 'households');
    case 'count':
      return formatCount(value);
    case 'ratio':
      return formatRatio(value, digits);
    case 'rank':
      return formatRank(value);
    case 'number':
      return formatNumber(value, digits);
    case 'date':
    case 'ym':
    case 'text':
      return String(value);
  }
}

/**
 * Fact → 표시 문자열. v가 null이면 null (호출 측이 "확인 불가(사유)"를 그린다).
 * 숫자 단위인데 v가 숫자 문자열이면 숫자로 해석한다.
 */
export function formatFactValue(
  fact: Fact,
  unit: FactUnit,
  options: FormatOptions = {},
): string | null {
  const { v } = fact;
  if (v === null || v === undefined) return null;
  if (unit === 'date') return formatDate(String(v), options.asof);
  if (unit === 'ym' || unit === 'text') return String(v);
  const n = typeof v === 'number' ? v : Number(v);
  if (typeof v === 'string' && (v.trim() === '' || !Number.isFinite(n))) return v;
  return formatValue(n, unit, options);
}

/** "확인 불가" / "확인 불가(사유)" */
export function formatUnknown(reason?: string | null): string {
  return reason ? t('empty.unknownWithReason', { reason }) : t('empty.unknown');
}
