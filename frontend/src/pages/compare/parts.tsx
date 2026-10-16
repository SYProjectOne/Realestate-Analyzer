/**
 * G4 비교·G5 내 조건이 같이 쓰는 화면 조각(R11-ANALYZE, 목업 Compare·Scenario 보드).
 * 숫자는 만들지 않는다 — 값 자리는 FactCell·MetaValue 를 children 으로 받는다. 문구는 ko.json.
 */
import type { ReactNode } from 'react';
import type { LadderHorizon, RequirementCheck, Scenario } from '@/api/types';
import { Badge, type BadgeTone, Card, MetaValue } from '@/components';
import { t, tDynamic } from '@/i18n';
import { enumText } from '../_shared';

/**
 * 목업 구역 카드: 작은 머리글(eyebrow) → 질문형 h2 → 한 줄 안내 → 본문. 구역 이름(aria-label)은 h2 질문.
 * `step` 이 있으면 h2 앞에 단계 번호 동그라미(G5 1~4).
 */
export function AnalyzeSection({
  eyebrow,
  title,
  hint,
  actions,
  step,
  children,
  className = '',
  'data-testid': testId,
}: {
  eyebrow?: ReactNode;
  title: string;
  hint?: ReactNode;
  actions?: ReactNode;
  step?: number;
  children: ReactNode;
  className?: string;
  'data-testid'?: string;
}) {
  return (
    <Card
      as="section"
      aria-label={title}
      padding="lg"
      data-testid={testId}
      className={`flex min-w-0 flex-col gap-4 ${className}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
        <div className="flex min-w-0 items-start gap-3">
          {step !== undefined ? (
            <span
              aria-hidden
              className="mt-1 inline-flex size-7 shrink-0 items-center justify-center rounded-full bg-fg text-sm font-bold text-surface"
            >
              <MetaValue kind="seq" value={step} as="plain" />
            </span>
          ) : null}
          <div className="flex min-w-0 flex-col gap-1">
            {eyebrow ? <p className="text-[13px] font-bold text-muted">{eyebrow}</p> : null}
            <h2 className="text-lg font-bold leading-snug text-fg sm:text-[22px]">{title}</h2>
            {hint ? <p className="text-sm leading-relaxed text-muted">{hint}</p> : null}
          </div>
        </div>
        {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
      </div>
      {children}
    </Card>
  );
}

/** 구역 바닥 한 줄(자료·기준일·고지) */
export function SourceLine({ children }: { children: ReactNode }) {
  return <p className="m-0 text-xs leading-relaxed text-muted">{children}</p>;
}

/** 쉬운 이름 + 회색 공식 이름 "(접수)" — 표 행 머리·칸 이름 */
export function PlainName({ name, official }: { name: string; official?: string | null }) {
  return (
    <>
      <span>{name}</span>
      {official ? <span className="text-xs font-normal text-muted"> ({official})</span> : null}
    </>
  );
}

/**
 * 단지 계열 기호(C01 겹쳐 보기와 같은 순서: 원·네모·세모·마름모·고리·둥근 네모). 색과 모양이 함께 계열을 가른다.
 */
export function SeriesMarker({ index, color }: { index: number; color: string }) {
  const shape = index % 6;
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden className="shrink-0">
      {shape === 0 ? <circle cx="6" cy="6" r="5" fill={color} /> : null}
      {shape === 1 ? <rect x="1.5" y="1.5" width="9" height="9" fill={color} /> : null}
      {shape === 2 ? <path d="M6 1 11.5 11H.5z" fill={color} /> : null}
      {shape === 3 ? <path d="M6 .5 11.5 6 6 11.5.5 6z" fill={color} /> : null}
      {shape === 4 ? (
        <circle cx="6" cy="6" r="4" fill="none" stroke={color} strokeWidth="2.5" />
      ) : null}
      {shape === 5 ? <rect x="1" y="1" width="10" height="10" rx="3" fill={color} /> : null}
    </svg>
  );
}

/** 요건 사전 계산 상태(충족·미충족·미입력·확인 불가) → 배지 톤. 의미는 글자(ko `page.G5.reqStatus`)가 나른다 */
export function reqTone(status: string): BadgeTone {
  switch (status) {
    case '충족':
      return 'accent';
    case '미충족':
      return 'neutral';
    case '미입력':
      return 'dashed';
    default:
      return 'caution';
  }
}

/** 요건 칸 상태 배지 */
export function ReqStatusBadge({ status }: { status: string }) {
  return (
    <span data-testid="req-status" data-status={status}>
      <Badge tone={reqTone(status)}>{enumText('page.G5.reqStatus', status)}</Badge>
    </span>
  );
}

/** 판정기 결론(supported·contradicted·unknown) → 쉬운 문장(ko `page.G4.reqJudge`). 없으면 그리지 않는다 */
export function ReqJudgeText({ judge }: { judge: RequirementCheck['judge'] }) {
  if (!judge) return null;
  return (
    <span className="text-xs text-muted" data-testid="req-judge" data-judge={judge}>
      {enumText('page.G4.reqJudge', judge)}
    </span>
  );
}

/** 라디오 알약 모양(목업 .rad) — 고른 것은 진한 바탕 */
export function radioClass(checked: boolean): string {
  return `min-h-11 rounded-full border px-3.5 text-sm ${
    checked
      ? 'border-fg bg-fg font-semibold text-surface'
      : 'border-border-strong bg-surface font-medium text-fg-2 hover:border-fg-2'
  }`;
}

/** 목업 .btn(흰 바탕 테두리 버튼·링크) */
export const outlineButtonClass =
  'inline-flex min-h-11 items-center gap-1.5 rounded-[10px] border border-border-strong bg-surface px-3.5 text-sm font-semibold text-fg hover:border-fg-2';

/** 목업 주 버튼(주색 바탕) */
export const primaryButtonClass =
  'inline-flex min-h-11 items-center gap-1.5 rounded-[10px] bg-accent px-4 text-sm font-semibold text-accent-fg disabled:opacity-50';

/** 대상 이름이 붙은 표 이름 머리 칸 공통 */
export const headCellClass =
  'border-b border-border px-3 py-2 text-left align-bottom text-sm font-semibold text-fg';
export const rowHeadClass =
  'w-56 min-w-40 border-b border-border bg-subtle px-3 py-3 text-left align-top text-sm font-medium text-fg-2';
export const cellClass = 'border-b border-border px-3 py-3 align-top text-sm';
/** 넓은 표 — 좁은 화면에서는 눌리지 않고 표 안에서 가로로 민다(overflow-x-auto 상자 안) */
export const wideTableClass = 'w-full min-w-[640px] border-collapse';

/** 목업 '오를 가능성' 고지(목표 시점 + 당첨 확률 아님 · 보장 아님) — 두 줄 */
export function P10Note({ target }: { target: string }) {
  return (
    <span className="mt-1 block text-xs font-normal leading-snug text-muted">
      <span className="block">{target}</span>
      <span className="block">{t('page.G4.row.p10Note')}</span>
    </span>
  );
}

/** 서버 목표 시점(p10_horizon·사다리 horizon) → 짧은 이름 "입주 + 1년" */
export function targetText(horizon: LadderHorizon | null | undefined): string | null {
  return horizon ? tDynamic(`page.G4.target.${horizon}`, horizon) : null;
}

/** 지금 상황의 '오를 가능성' 목표 시점 줄 — 시나리오 policy.p10_horizon(서버 값) */
export function p10TargetLine(scenario: Pick<Scenario, 'name' | 'policy'> | null): string {
  const target = targetText(scenario?.policy?.p10_horizon);
  return scenario && target
    ? t('page.G4.row.p10Target', { target, name: scenario.name })
    : t('page.G4.row.p10TargetUnknown');
}
