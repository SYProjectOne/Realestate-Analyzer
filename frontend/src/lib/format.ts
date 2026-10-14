/**
 * 숫자·날짜 포맷 — 화면에서 숫자를 문자열로 바꾸는 유일한 곳 (AGENTS 규칙 12, RA §7).
 * 컴포넌트는 FactCell을 쓰고, 차트 축·툴팁·표 셀은 여기 함수를 쓴다.
 * 단위 문자열(억·만·원·㎡·세대·D-day)도 ko.json에서 온다.
 */
import { t, type TKey } from '@/i18n';
import type { FactLike } from './contract';

/** ISO 날짜 `YYYY-MM-DD` */
export type IsoDate = string;

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
  /** 계약 Fact.unit 'units'(세대) — households와 같다 */
  | 'units'
  /** 연도 → "2028" (천 단위 구분 없음) */
  | 'year'
  /** 개월 → "24개월" */
  | 'months'
  /** 년 → "5년" */
  | 'years'
  /** 미터 → "350m" */
  | 'm'
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

/** 자릿수별 숫자 포맷터(만들기 비싸다 — 표 스크롤 프레임마다 셀 수십 개가 부른다, T16) */
const nfCache = new Map<number, Intl.NumberFormat>();
const nf = (digits = 0): Intl.NumberFormat => {
  let f = nfCache.get(digits);
  if (!f) {
    f = new Intl.NumberFormat('ko-KR', {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    });
    nfCache.set(digits, f);
  }
  return f;
};

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

/**
 * 판정기 신뢰도(decide confidence·봉투 confidence, 0~1 원값) → "0.48". 확률(%)이 아니라 판정기 자기 평가라
 * 소수 둘째 자리 그대로 보인다(meta §2-7 표기). 범위 밖·NaN 이면 "확인 불가".
 */
export function formatConfidence(confidence: number): string {
  if (!Number.isFinite(confidence) || confidence < 0 || confidence > 1) return unknown();
  return nf(2).format(confidence);
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

/** KST = UTC+9 (일광 절약 없음) */
const KST_OFFSET_MS = 9 * 3_600_000;

/** `YYYY-MM-DD[T hh:mm[:ss[.fff]]][Z|±hh:mm]` — `T`·`Z` 는 대소문자 무관(D15-7) */
const ISO_RE =
  /^(\d{4})-(\d{2})-(\d{2})(?:[Tt ](\d{2}):(\d{2})(?::(\d{2})(?:[.,]\d+)?)?\s*([Zz]|[+-]\d{2}:?\d{2})?)?/;

/**
 * ISO 날짜/일시 → **KST 날짜** `YYYY-MM-DD` (D15-7·D16-5 — 화면의 날짜 표시는 모두 KST, R3 8차 m13).
 * 시간대가 붙은 시각(`…Z`, `…+00:00`, `…-05:00`)은 KST 로 옮긴 날짜다: `2026-10-09T20:00:00Z` → `2026-10-10`.
 * 날짜만(`2026-10-09`)이거나 시간대가 없는 시각은 이미 그 날짜로 적힌 값이라 그대로 둔다(브라우저 시간대를 쓰지 않는다).
 * 형식이 아니면 null.
 */
export function kstDay(iso: string): IsoDate | null {
  const parts = kstParts(iso);
  return parts ? `${parts.yyyy}-${parts.mm}-${parts.dd}` : null;
}

/**
 * ISO 일시 → **KST** `YYYY-MM-DD hh:mm`(계약 .18 F3 — 지연 재큐잉 다음 시도 시각 `not_before`). 규칙은 `kstDay` 와 같다
 * (시간대 붙은 시각은 KST 로 옮기고, 시간대 없는 시각은 적힌 그대로). 시각이 없으면 날짜만, 형식이 아니면 받은 문자열 그대로.
 */
export function kstDateTime(iso: string): string {
  const parts = kstParts(iso);
  if (!parts) return iso;
  const day = `${parts.yyyy}-${parts.mm}-${parts.dd}`;
  return parts.hh === null ? day : `${day} ${parts.hh}:${parts.mi ?? '00'}`;
}

interface KstParts {
  yyyy: string;
  mm: string;
  dd: string;
  hh: string | null;
  mi: string | null;
}

function kstParts(iso: string): KstParts | null {
  const m = ISO_RE.exec(iso);
  if (!m) return null;
  const [, y, mo, d, h, mi, s, zone] = m;
  const asWritten: KstParts = {
    yyyy: y ?? '',
    mm: mo ?? '',
    dd: d ?? '',
    hh: h ?? null,
    mi: mi ?? null,
  };
  if (h === undefined || zone === undefined) return asWritten;
  let offsetMin = 0;
  if (zone !== 'Z' && zone !== 'z') {
    const z = /^([+-])(\d{2}):?(\d{2})$/.exec(zone);
    if (!z) return asWritten;
    offsetMin = (z[1] === '-' ? -1 : 1) * (Number(z[2]) * 60 + Number(z[3]));
  }
  // Date.UTC 는 0~99 년을 1900 년대로 바꾼다 — setUTCFullYear 로
  const at = new Date(0);
  at.setUTCFullYear(Number(y), Number(mo) - 1, Number(d));
  at.setUTCHours(Number(h), Number(mi), Number(s ?? 0), 0);
  const kst = new Date(at.getTime() - offsetMin * 60_000 + KST_OFFSET_MS);
  if (Number.isNaN(kst.getTime())) return asWritten;
  return {
    yyyy: String(kst.getUTCFullYear()).padStart(4, '0'),
    mm: String(kst.getUTCMonth() + 1).padStart(2, '0'),
    dd: String(kst.getUTCDate()).padStart(2, '0'),
    hh: String(kst.getUTCHours()).padStart(2, '0'),
    mi: String(kst.getUTCMinutes()).padStart(2, '0'),
  };
}

/** ISO 날짜/일시의 KST 날짜 → UTC 기준 일수 (브라우저 시간대 영향 없음) */
function toDayNumber(iso: string): number | null {
  const kst = kstDay(iso);
  if (kst === null) return null;
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(kst);
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

/** "2026-10-11" 또는 기준일이 있으면 "2026-10-11 (D-3)". 시각은 KST 날짜로(`kstDay`) */
export function formatDate(date: string, asof?: string | null): string {
  const day = kstDay(date);
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
    case 'units':
      return formatCount(value, 'households');
    case 'year':
      return String(Math.round(value));
    case 'months':
      return t('unit.months', { n: formatNumber(value, digits ?? 0) });
    case 'years':
      return t('unit.years', { n: formatNumber(value, digits ?? 0) });
    case 'm':
      return `${formatNumber(value, digits ?? 0)}${t('unit.meter')}`;
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
  fact: FactLike,
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

/** 계약 .20 사유 코드(fact.json ReasonCode — 서버 `app.api.reason_codes`) */
export type ReasonCode = NonNullable<FactLike['reason_code']>;

/**
 * 사유 코드 → 쉬운 말 key(R9-UI P7, 계약 .20 F3). `no_value` 는 서버 사유가 이미 구체적인 말('1순위 해당지역 경쟁률 없음')이라
 * 바꾸지 않는다(일반 문구로 바꾸면 뜻이 흐려진다). 코드가 'other'·없음(.20 이전 발행 저장본)이면 서버 사유 그대로 —
 * 화면이 문자열로 사유를 추측하지 않는다. 원 사유(reason)는 title·출처 패널.
 */
const REASON_PLAIN: Partial<Record<ReasonCode, TKey>> = {
  fetch_failed: 'empty.reasonPlain.fetch_failed',
  not_collected: 'empty.reasonPlain.not_collected',
  not_published: 'empty.reasonPlain.pre_notice',
  parse_failed: 'empty.reasonPlain.parse_failed',
  source_missing: 'empty.reasonPlain.source_missing',
  demoted: 'empty.reasonPlain.demoted',
  conflict_hold: 'empty.reasonPlain.conflict_hold',
  partial_missing: 'empty.reasonPlain.partial_missing',
  identity_unconfirmed: 'empty.reasonPlain.identity_unconfirmed',
  other_complex_site: 'empty.reasonPlain.other_complex_site',
  no_phrase: 'empty.reasonPlain.no_phrase',
  phrase_inconclusive: 'empty.reasonPlain.phrase_inconclusive',
  not_target: 'empty.reasonPlain.not_target',
  input_blocked: 'empty.reasonPlain.input_blocked',
  unresolved: 'empty.reasonPlain.unresolved',
  unjudged: 'empty.reasonPlain.unjudged',
  not_entered: 'empty.reasonPlain.not_entered',
  no_sample: 'empty.reasonPlain.no_sample',
  human_check: 'empty.reasonPlain.human_check',
};

/** 사유 → 화면 문구. 코드가 없거나 표에 없으면 서버 사유 그대로(mapped=false) */
export function plainReason(
  reason: string,
  code?: ReasonCode | null,
): { text: string; mapped: boolean } {
  // 수집 실패는 짧은 기술 사유(403·DNS·TLS)가 운영·사람 확인에 쓸모 있어 함께 둔다
  if (code === 'fetch_failed') {
    return { text: t('empty.reasonPlain.fetch_failedWith', { reason }), mapped: true };
  }
  const key = code ? REASON_PLAIN[code] : undefined;
  return key ? { text: t(key), mapped: true } : { text: reason, mapped: false };
}

/** 쉬운 말로 바꾼 사유면 "원래 사유: …"(같은 요소의 title — 0클릭, 마우스 올림). 아니면 undefined */
export function unknownTitle(
  reason: string | null | undefined,
  code?: ReasonCode | null,
): string | undefined {
  if (!reason || !plainReason(reason, code).mapped) return undefined;
  return t('empty.reasonOriginal', { reason });
}

/**
 * "확인 불가" / "확인 불가(사유)" / "확인 불가(사유, 확인일)" — 계약 fact.json 표시 규칙 1.
 * 괄호 안 사유는 사유 코드(`code`, 계약 .20)의 쉬운 말(P7). `raw` 면 서버 사유 그대로(출처 패널 '라벨' 줄).
 */
export function formatUnknown(
  reason?: string | null,
  checkedAt?: string | null,
  options: { raw?: boolean; code?: ReasonCode | null } = {},
): string {
  if (!reason) return t('empty.unknown');
  const shown = options.raw ? reason : plainReason(reason, options.code).text;
  const date = checkedAt ? (kstDay(checkedAt) ?? undefined) : undefined;
  return date
    ? t('empty.unknownWithReasonDate', { reason: shown, date })
    : t('empty.unknownWithReason', { reason: shown });
}

/** 계약 Fact.unit 힌트 → FactUnit (FactCell에서 unit prop을 생략했을 때). 숫자면 'number', 아니면 'text' */
export function unitFromHint(hint: string | null | undefined, v: unknown): FactUnit {
  switch (hint) {
    case 'won':
    case 'm2':
    case 'pct':
    case 'prob':
    case 'score':
    case 'units':
    case 'count':
    case 'date':
    case 'ym':
    case 'year':
    case 'months':
    case 'years':
    case 'm':
    case 'text':
      return hint;
    case 'ratio':
      // 계약 ratio = 0~1 비율 → 퍼센트로
      return 'prob';
    default:
      return typeof v === 'number' ? 'number' : 'text';
  }
}
