/** 차트 공개 API — 계약은 ./README.md. 화면(WP6a)은 여기서만 import 한다. */
export { ChartFrame, type ChartFrameProps } from './ChartFrame';
export { ChartLegend } from './ChartLegend';
export { ChartFooter, type ChartFooterProps } from './ChartTable';
export { EChart, type EChartProps } from './EChart';
export { DEFAULT_PALETTE, useChartPalette } from './palette';
export { chartModules, chartRegistry, type ChartDataMap } from './registry';
export type {
  BuildOptionContext,
  ChartId,
  ChartLegendItem,
  ChartLegendSymbol,
  ChartModule,
  ChartPalette,
  EChartsOption,
} from './types';

export { C01Ladder, type C01LadderProps } from './C01';
export type { C01Data, C01OverlaySeries } from './C01/types';
export { C02Gap, type C02GapProps } from './C02';
export type { C02Data } from './C02/types';
export { C03Benchmark, type C03BenchmarkProps } from './C03';
export type { C03Data } from './C03/types';
export { C04Supply, type C04SupplyProps } from './C04';
export type { C04Data, C04Marker } from './C04/types';
export { C05Unsold, type C05UnsoldProps } from './C05';
export type { C05Data } from './C05/types';
export { C06ScoreBreakdown, type C06ScoreBreakdownProps } from './C06';
export type { C06Data } from './C06/types';
export { C07Decision, type C07DecisionProps } from './C07';
export type { C07Data } from './C07/types';
export { C08Timeline, type C08TimelineProps } from './C08';
export type { C08Data } from './C08/types';
export { C09Catalyst, type C09CatalystProps } from './C09';
export type { C09Data } from './C09/types';
export { C10Sensitivity, type C10SensitivityProps } from './C10';
export type { C10Data } from './C10/types';
