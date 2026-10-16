import { useScenarios } from '@/api/hooks';
import type { ComplexDetail } from '@/api/types';
import {
  Badge,
  BigNumber,
  FactCell,
  FactList,
  FactRow,
  MetaText,
  MetaValue,
  Term,
  TieBadge,
  UnstableBadge,
} from '@/components';
import { t } from '@/i18n';
import { formatHalfYear } from '@/lib/format';
import { enumText, JudgeScopeBadge, RejudgeNeededBadge, ScopeReason, unitOf } from '../_shared';
import { Tier } from './Tier';

/** 점수 성분 순서(RA §6 — 종합 = Σ 비중 × 성분). liquidity·move_in 은 상황이 쓰는 하나만 온다 */
const COMPONENT_KEYS = [
  'p10',
  'rerank',
  'gap',
  'benchmark',
  'supply',
  'liquidity',
  'move_in',
] as const;
type ComponentKey = (typeof COMPONENT_KEYS)[number];
type Score = NonNullable<ComplexDetail['score']>;
type ComponentView = NonNullable<Score['components'][ComponentKey]>;

/** 성분 막대 폭(0~10 점수 → %) — 서버 점수 그대로 그리는 장식. 값·라벨은 FactCell */
function barWidth(view: ComponentView): number {
  const v = Number(view.score.v);
  return Number.isFinite(v) ? Math.max(0, Math.min(v * 10, 100)) : 0;
}

/**
 * 점수는 왜 이렇게 나왔나요? — 종합 점수(+ 순위·동률·불안정·판정 범위·재판정 배지) + 성분별 쉬운 이름 · 비중 · 성분 점수 · 원값.
 * +10% 성분에는 목표 시점(상황의 p10_horizon — 고정 문구로 쓰지 않는다)과 "당첨 확률이 아니에요 · 보장 아님"을 붙인다.
 * 성분 근거 문장은 짓지 않는다(규칙 3) — 식(formula_text, 서버 문구)은 줄 title.
 */
export function ScoreCard({ detail }: { detail: ComplexDetail }) {
  const { score, header } = detail;
  const { data: scenarios = [] } = useScenarios();
  const horizon = scenarios.find((s) => s.id === detail.scenario_id)?.policy.p10_horizon ?? null;
  const ladderRow = horizon ? detail.ladder.find((r) => r.horizon === horizon) : undefined;
  const target = ladderRow ? (ladderRow.target_label ?? formatHalfYear(ladderRow.target_ym)) : null;
  const views = score
    ? COMPONENT_KEYS.flatMap((k) => {
        const view = score.components[k];
        return view ? [{ key: k, view }] : [];
      })
    : [];
  return (
    <Tier tier="score" title={t('page.G3.summary.score')} hint={t('page.G3.summary.scoreHint')}>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <BigNumber
          size="xl"
          data-testid="score-total"
          label={
            <span className="inline-flex items-center gap-1">
              {t('page.G3.header.total')}
              <Term k="total" />
            </span>
          }
        >
          {score ? (
            <FactCell wrap fact={score.total} unit="score" />
          ) : (
            <FactCell fact={null} unit="score" emptyReason={t('page.G3.scoreWhy.none')} />
          )}
        </BigNumber>
        {score ? (
          <span className="flex flex-wrap items-center gap-1">
            {score.rank !== null ? (
              <Badge tone="strong">
                <MetaValue kind="rank" value={score.rank} as="rank" />
              </Badge>
            ) : null}
            <TieBadge tie={score.tie_group !== null} />
            <UnstableBadge unstable={score.unstable} />
            <JudgeScopeBadge scope={score.judge_scope} />
            <RejudgeNeededBadge needed={score.rejudge_needed} />
          </span>
        ) : null}
      </div>

      {views.length > 0 ? (
        <ul aria-label={t('page.G3.scoreWhy.list')} className="flex flex-col gap-3">
          {views.map(({ key, view }) => (
            <li
              key={key}
              data-component={key}
              title={view.formula_text}
              className="flex flex-col gap-1"
            >
              <span className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                <span className="flex flex-wrap items-baseline gap-2">
                  <span className="text-sm font-semibold text-fg">
                    {t(`page.G3.scoreWhy.component.${key}`)}
                  </span>
                  <MetaText
                    kind="input"
                    k="page.G3.scoreWhy.weight"
                    params={{ w: { n: view.weight, as: 'prob' } }}
                    className="text-xs text-muted"
                  />
                </span>
                <span className="text-sm font-bold">
                  <FactCell wrap fact={view.score} unit="score" digits={1} />
                </span>
              </span>
              <span aria-hidden className="h-1.5 w-full overflow-hidden rounded-full bg-chip">
                <span
                  className="block h-full rounded-full bg-accent"
                  style={{ width: `${barWidth(view)}%` }}
                />
              </span>
              {view.raw ? (
                <span className="flex flex-wrap items-center gap-1 text-xs text-muted">
                  <span>{t('page.G3.scoreWhy.raw')}</span>
                  <FactCell wrap fact={view.raw} unit={unitOf(view.raw, 'number')} />
                </span>
              ) : null}
              {key === 'p10' ? (
                <span className="flex flex-col text-xs text-muted" data-testid="score-p10-note">
                  {horizon && target ? (
                    <span>
                      {t('page.G3.scoreWhy.p10Target', {
                        horizon: enumText('chart.C01.horizon', horizon),
                        target,
                      })}
                    </span>
                  ) : null}
                  <span>{t('page.G3.scoreWhy.p10Note')}</span>
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}

      <FactList>
        {score?.delta_rerank ? (
          <FactRow label={t('page.common.deltaRerank')}>
            <FactCell wrap fact={score.delta_rerank} unit="score" />
          </FactRow>
        ) : null}
        <FactRow
          label={
            <span className="inline-flex items-center gap-1">
              {t('page.G3.header.inclusion')}
              <Term k="inclusion" />
            </span>
          }
        >
          <span className="inline-flex flex-wrap items-center justify-end gap-1">
            {enumText('page.common.inclusion', header.inclusion_class)}
            <FactCell wrap fact={header.inclusion_prob} unit="prob" />
          </span>
        </FactRow>
        {header.judge_scope_reason ? (
          // 계약 .17 F1(D22-5)·.22 W4·W5(D30-6): 판정 범위 사유 — 서버 문자열 그대로(한국어 분류명). 키 없음(.16 저장본)이면 칸 없음
          <FactRow
            layout="stack"
            label={
              <span className="inline-flex items-center gap-1">
                {t('page.G3.header.scopeReason')}
                <Term k="judge_scope" />
              </span>
            }
          >
            <ScopeReason
              reason={header.judge_scope_reason}
              rejudgeNeeded={score?.rejudge_needed ?? false}
              testId="scope-reason"
            />
          </FactRow>
        ) : null}
      </FactList>
    </Tier>
  );
}
