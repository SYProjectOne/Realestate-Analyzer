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
  /** 두 번째 계열(주황 — 파랑 strong과 밝기가 다르다. C05 준공 후 등) */
  secondary: string;
  /** 강조색의 옅은 단계(C07 선택 안 된 후보, C01 점수에 안 쓰는 막대) */
  strongSoft: string;
  /** '나머지 n곳'처럼 묶은 계열 */
  rest: string;
  /** 옅은 격자선 */
  grid: string;
  /** 띠 영역(C10 '상위 5곳 밖') */
  band: string;
}

/** 차트 위 HTML 범례 한 줄(ChartLegend). 색 + 모양 + 글자 — 색만으로 구분하지 않는다 */
export type ChartLegendSymbol =
  | 'square'
  | 'circle'
  | 'ring'
  | 'dashedRing'
  | 'rect'
  | 'triangle'
  | 'triangleDown'
  | 'diamond'
  | 'pin'
  | 'line'
  | 'dashedLine'
  | 'range'
  | 'tick'
  | 'hatch';

export interface ChartLegendItem {
  /** 보이는 이름(ko.json에서 온 문자열 또는 서버 이름) */
  name: string;
  color: string;
  symbol: ChartLegendSymbol;
  /** 이름 옆 작은 회색 글자(예: '비중 35%') */
  note?: string;
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
  /** 차트 위 범례(HTML). 계열이 하나뿐이면 빈 배열 */
  legendItems: (data: D, ctx?: BuildOptionContext) => ChartLegendItem[];
}
