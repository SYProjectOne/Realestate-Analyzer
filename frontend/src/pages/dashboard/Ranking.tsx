import { useMemo, type MouseEvent } from 'react';
import { Link, useNavigate } from 'react-router';
import type { Dashboard, ScoreRow } from '@/api/types';
import {
  ChartFooter,
  ChartLegend,
  chartModules,
  EChart,
  useChartPalette,
  type C06Data,
  type ChartPalette,
  type EChartsOption,
} from '@/charts';
import {
  Card,
  FactCell,
  IntakeBadge,
  LabelBadge,
  MetaText,
  MetaValue,
  SectionHeader,
  Term,
  TieBadge,
  UnstableBadge,
} from '@/components';
import { t } from '@/i18n';
import { JudgeScopeBadge, RejudgeNeededBadge, useGlobalSearch } from '../_shared';

/** 성분 점수 만점(0~10) — 모든 줄 막대가 같은 축 길이를 쓴다 */
const SCORE_MAX = 10;
/** 줄 막대 높이(px) · 마지막 줄은 점수 축 눈금 자리를 더한다 */
const BAR_HEIGHT = 30;
const AXIS_HEIGHT = 24;

type Axis = Record<string, unknown>;

/**
 * C06 한 줄 막대(고침 HM-8): C06 차트 모듈의 option(가로·쌓은 막대 · 성분 색 · 툴팁 = 점수 × 비중 · 기여 · 원값 · 산출식 ·
 * 미판정 빗금)을 그대로 쓰고, 줄 안에 넣으려고 바깥 모양만 바꾼다 — 이름 축은 줄 글자가 대신하고(숨김), 점수 축은 0~10 으로
 * 고정해 줄끼리 길이를 맞추며, 눈금은 마지막 줄에만 보인다. 값·색·툴팁은 바꾸지 않는다.
 */
export function rowBarOption(
  row: ScoreRow,
  data: Pick<C06Data, 'weights' | 'keys'>,
  palette: ChartPalette,
  showAxis: boolean,
): EChartsOption {
  const base = chartModules.C06.buildOption(
    { rows: [row], weights: data.weights, keys: data.keys, orientation: 'horizontal' },
    { palette },
  ) as Record<string, unknown>;
  const xAxis = (base.xAxis ?? {}) as Axis;
  const yAxis = (base.yAxis ?? {}) as Axis;
  return {
    ...base,
    grid: { left: 2, right: 8, top: 2, bottom: showAxis ? AXIS_HEIGHT : 2 },
    // 미판정 메모는 구역 범례(빗금 = 미판정)로 한 번만
    graphic: [],
    xAxis: {
      ...xAxis,
      max: SCORE_MAX,
      name: '',
      show: showAxis,
      splitLine: { show: false },
    },
    yAxis: { ...yAxis, show: false },
  } as EChartsOption;
}

function RowBar({
  row,
  data,
  showAxis,
}: {
  row: ScoreRow;
  data: Pick<C06Data, 'weights' | 'keys'>;
  showAxis: boolean;
}) {
  const palette = useChartPalette();
  const option = useMemo(
    () => rowBarOption(row, data, palette, showAxis),
    [row, data, palette, showAxis],
  );
  return (
    <EChart
      option={option}
      height={BAR_HEIGHT + (showAxis ? AXIS_HEIGHT : 0)}
      ariaLabel={t('page.G1.rankBar', { name: row.name })}
    />
  );
}

/**
 * '점수 순서 · 상황: {이름}'(Main 보드): 순위 5 이하 줄마다 사실(현재 구매가·주변 시세와 차이·전매 종료) → '+10% 이상 오를
 * 가능성'(목표 시점 · 당첨 확률 아님 · 보장 아님) → C06 점수 구성 막대 → 종합 점수. 범례·비중은 머리에 한 번, 표로 보기는 바닥.
 */
export function Ranking({ data, target }: { data: Dashboard; target: string | null }) {
  const palette = useChartPalette();
  const rows = data.top5.filter((row) => row.rank === null || row.rank <= 5);
  const chartData: C06Data = { rows, weights: data.weights, orientation: 'horizontal' };
  const legend = chartModules.C06.legendItems(chartData, { palette });
  const table = chartModules.C06.toTable(chartData);
  const labels = [...new Set(rows.map((row) => row.total.label))];
  const title = t('page.G1.top5');
  const barData = useMemo(() => ({ weights: data.weights }), [data.weights]);
  return (
    <Card as="section" aria-label={title} data-section="top" className="flex flex-col gap-4">
      <SectionHeader
        title={`${title} · ${t('page.G1.top5Scenario', { name: data.scenario_name })}`}
        hint={t('page.G1.top5Note')}
      />
      <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[13px] text-fg-2">
        <span className="inline-flex items-center gap-1">
          {t('page.G1.total')}
          <Term k="total" />
        </span>
        <span className="inline-flex items-center gap-1">
          {t('page.G1.p10')}
          <Term k="p10" />
        </span>
      </p>
      <ChartLegend items={legend} />
      {rows.length < 5 ? (
        <p data-testid="top5-fewer" className="text-sm text-muted">
          <MetaText kind="count" k="page.G1.top5Fewer" params={{ n: rows.length }} />
        </p>
      ) : null}
      <ol aria-label={title} className="flex flex-col divide-y divide-border">
        {rows.map((row, i) => (
          <RankRow
            key={row.complex_id}
            row={row}
            asof={data.asof_date}
            target={target}
            barData={barData}
            showAxis={i === rows.length - 1}
          />
        ))}
      </ol>
      <ChartFooter
        table={table}
        caption={t('chart.C06.title')}
        source={
          <span className="inline-flex flex-wrap items-center gap-1.5">
            <span>{t('page.G1.total')}</span>
            {labels.map((label) => (
              <LabelBadge key={label} label={label} />
            ))}
            <span aria-hidden>·</span>
            <span>{t('chart.source', { source: t('chart.C06.source') })}</span>
          </span>
        }
        asof={data.asof_date}
      />
    </Card>
  );
}

/**
 * 점수 줄(D28-4 '사실 먼저·점수 아래'): 순위 · 이름 · 배지(동률·접수·흔들림·범위·다시 판정) → 생활권 · 사실 칸 →
 * '+10% 이상 오를 가능성' 줄 → 막대 → 종합. 줄 빈 곳을 누르면 단지 상세(안쪽 버튼·링크는 그대로, 고침 HM-17 #58).
 * .20 이전 발행 저장본(키 없음)은 '확인 불가(이 기준일 자료에 없음)'.
 */
function RankRow({
  row,
  asof,
  target,
  barData,
  showAxis,
}: {
  row: ScoreRow;
  asof: string;
  target: string | null;
  barData: Pick<C06Data, 'weights' | 'keys'>;
  showAxis: boolean;
}) {
  const navigate = useNavigate();
  const search = useGlobalSearch();
  const to = `/complexes/${row.complex_id}${search}`;
  const onClick = (event: MouseEvent<HTMLLIElement>) => {
    if ((event.target as HTMLElement).closest('button, a, summary, [role="img"]')) return;
    navigate(to);
  };
  const missing = t('page.G1.noListRow');
  const tie = row.tie_group !== null || row.decision?.tie === true;
  return (
    <li
      onClick={onClick}
      data-complex-id={row.complex_id}
      className="grid cursor-pointer grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-2 py-4 lg:grid-cols-[auto_minmax(0,400px)_minmax(0,1fr)_auto] lg:items-center"
    >
      <span
        aria-hidden={row.rank === null}
        className={`row-span-2 flex size-9 items-center justify-center self-start rounded-full text-sm font-bold lg:row-span-1 lg:self-center ${
          row.rank === 1 ? 'bg-accent text-accent-fg' : 'bg-accent-soft text-accent-ink'
        }`}
      >
        {row.rank !== null ? <MetaValue kind="rank" value={row.rank} as="number" /> : null}
      </span>
      <div className="flex min-w-0 flex-col gap-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <Link
            to={to}
            className="text-base font-bold text-fg hover:underline"
            aria-label={t('page.G1.open', { name: row.name })}
          >
            {row.name}
          </Link>
          <TieBadge
            tie={tie}
            confidence={row.decision?.tie ? (row.decision.confidence ?? null) : null}
          />
          <IntakeBadge intake={row.intake} asof={asof} />
          <UnstableBadge unstable={row.unstable} />
          <JudgeScopeBadge scope={row.judge_scope} hideTarget />
          <RejudgeNeededBadge needed={row.rejudge_needed} />
        </div>
        <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs">
          {row.living_area_name ? (
            <span className="text-muted" data-field="living_area">
              {row.living_area_name}
            </span>
          ) : null}
          <dl data-card="facts" className="contents">
            <dt className="text-muted">{t('page.G1.card.price')}</dt>
            <dd className="flex flex-wrap items-center gap-1">
              <FactCell wrap fact={row.price_low ?? null} unit="won" emptyReason={missing} />
              <span aria-hidden>~</span>
              <FactCell wrap fact={row.price_high ?? null} unit="won" emptyReason={missing} />
            </dd>
            <dt className="text-muted">{t('page.G1.card.gap')}</dt>
            <dd>
              <FactCell wrap fact={row.gap_pct ?? null} unit="pct" emptyReason={missing} />
            </dd>
            <dt className="text-muted">{t('page.G1.card.resaleEnd')}</dt>
            <dd>
              <FactCell
                wrap
                fact={row.resale_end ?? null}
                unit="date"
                asof={asof}
                emptyReason={missing}
              />
            </dd>
          </dl>
        </div>
        <p data-card="p10" className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-xs">
          <span className="text-fg-2">{t('page.G1.p10Line')}</span>
          <FactCell wrap fact={row.p10} unit="prob" />
          <span aria-hidden className="text-muted">
            ·
          </span>
          <span className="text-muted" data-testid="p10-target">
            {t('page.G1.p10Target', { target: target ?? t('empty.unknown') })}
          </span>
          <span aria-hidden className="text-muted">
            ·
          </span>
          <span className="text-muted">{t('page.G1.p10Note')}</span>
        </p>
      </div>
      <div className="col-start-2 min-w-0 lg:col-start-3" data-card="bar">
        <RowBar row={row} data={barData} showAxis={showAxis} />
      </div>
      <div
        data-card="score"
        className="col-start-2 flex items-baseline gap-1.5 text-xl font-bold lg:col-start-4 lg:row-start-1 lg:justify-end"
      >
        <span className="text-xs font-normal text-muted lg:sr-only">{t('page.G1.total')}</span>
        <FactCell wrap fact={row.total} unit="score" />
      </div>
    </li>
  );
}
