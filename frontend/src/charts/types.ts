import type { EChartsOption } from 'echarts';
import type { DataTable } from '@/components/DataTableToggle';
import type { TKey } from '@/i18n';

export type { EChartsOption };

export const CHART_IDS = [
  'C01',
  'C02',
  'C03',
  'C04',
  'C05',
  'C06',
  'C07',
  'C08',
  'C09',
  'C10',
] as const;
export type ChartId = (typeof CHART_IDS)[number];

/**
 * 차트 색. CSS 토큰(src/index.css)에서 읽어 라이트/다크를 따른다(useChartPalette).
 * 의미 색은 strong(확정·강조)과 grayed(비공식·미확정·미해결) 둘뿐. 계열 구분은 categorical.
 */
export interface ChartPalette {
  fg: string;
  muted: string;
  border: string;
  bg: string;
  strong: string;
  grayed: string;
  /** 계열 구분(C04 생활권 스택, C06 6요소 등). 색만으로 의미를 전하지 않는다 — 범례·라벨 병기 */
  categorical: string[];
}

export interface BuildOptionContext {
  palette: ChartPalette;
}

/**
 * 차트 모듈 계약 — C01~C10 폴더가 각각 이 모양을 지킨다.
 *  - buildOption: 데이터 → ECharts option. **순수 함수**(DOM·훅·전역 상태 금지). 빈 데이터에서도 throw 금지.
 *  - emptyReason: 그릴 게 없으면 화면에 띄울 문구(ko.json), 있으면 null
 *  - toTable: "표로 보기"용 표 (D7)
 */
export interface ChartModule<D> {
  id: ChartId;
  titleKey: TKey;
  /** 빈 데이터 예시 — 테스트·스토리·로딩 자리표시 */
  empty: D;
  buildOption: (data: D, ctx?: BuildOptionContext) => EChartsOption;
  emptyReason: (data: D) => string | null;
  toTable: (data: D) => DataTable;
}
