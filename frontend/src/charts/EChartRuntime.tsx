/**
 * ECharts 런타임 — 쓰는 차트·컴포넌트만 등록한다(트리 셰이킹, 최대 청크 ≤ 500kB — R3c).
 * C01~C10 buildOption 이 쓰는 것: bar·line·scatter·custom 계열, grid·tooltip(axisPointer)·legend·
 * markLine·markPoint·graphic·aria, labelLayout, SVG 렌더러. 새 계열·컴포넌트를 쓰면 여기에 등록한다
 * (EChartRuntime.test.ts 가 buildOption 결과의 series.type 을 이 목록과 대조한다).
 * EChart.tsx 가 lazy 로 불러 첫 화면 번들에 들어가지 않는다.
 */
import ReactEChartsCore from 'echarts-for-react/lib/core';
import type { EChartsReactProps } from 'echarts-for-react/lib/types';
import { BarChart, CustomChart, LineChart, ScatterChart } from 'echarts/charts';
import {
  AriaComponent,
  AxisPointerComponent,
  GraphicComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  MarkPointComponent,
  TooltipComponent,
} from 'echarts/components';
import * as echarts from 'echarts/core';
import { LabelLayout } from 'echarts/features';
import { SVGRenderer } from 'echarts/renderers';

/** 등록한 series.type — 테스트가 buildOption 결과와 대조한다 */
export const REGISTERED_SERIES = ['bar', 'line', 'scatter', 'custom'] as const;

echarts.use([
  BarChart,
  LineChart,
  ScatterChart,
  CustomChart,
  GridComponent,
  TooltipComponent,
  AxisPointerComponent,
  LegendComponent,
  MarkLineComponent,
  MarkPointComponent,
  GraphicComponent,
  AriaComponent,
  LabelLayout,
  SVGRenderer,
]);

export default function EChartRuntime(props: Omit<EChartsReactProps, 'echarts'>) {
  return <ReactEChartsCore echarts={echarts} {...props} />;
}
