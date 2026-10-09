/**
 * 차트 모듈 10개의 순수 부분(buildOption·emptyReason·toTable·empty) 목록.
 * 테스트(빈 데이터 throw 없음)와 보고서 option 생성 검증이 이걸 순회한다. React 컴포넌트는 ./index.ts.
 */
import * as C01 from './C01/buildOption';
import { C01_EMPTY, type C01Data } from './C01/types';
import * as C02 from './C02/buildOption';
import { C02_EMPTY, type C02Data } from './C02/types';
import * as C03 from './C03/buildOption';
import { C03_EMPTY, type C03Data } from './C03/types';
import * as C04 from './C04/buildOption';
import { C04_EMPTY, type C04Data } from './C04/types';
import * as C05 from './C05/buildOption';
import { C05_EMPTY, type C05Data } from './C05/types';
import * as C06 from './C06/buildOption';
import { C06_EMPTY, type C06Data } from './C06/types';
import * as C07 from './C07/buildOption';
import { C07_EMPTY, type C07Data } from './C07/types';
import * as C08 from './C08/buildOption';
import { C08_EMPTY, type C08Data } from './C08/types';
import * as C09 from './C09/buildOption';
import { C09_EMPTY, type C09Data } from './C09/types';
import * as C10 from './C10/buildOption';
import { C10_EMPTY, type C10Data } from './C10/types';
import type { BuildOptionContext, ChartId, ChartModule, EChartsOption } from './types';
import type { DataTable } from '@/components/DataTableToggle';
import type { TKey } from '@/i18n';

export interface ChartDataMap {
  C01: C01Data;
  C02: C02Data;
  C03: C03Data;
  C04: C04Data;
  C05: C05Data;
  C06: C06Data;
  C07: C07Data;
  C08: C08Data;
  C09: C09Data;
  C10: C10Data;
}

/** 이질적인 모듈을 한 배열에 담기 위한 타입 지운 항목 */
export interface ChartRegistryEntry {
  id: ChartId;
  titleKey: TKey;
  empty: unknown;
  buildOption: (data: unknown, ctx?: BuildOptionContext) => EChartsOption;
  emptyReason: (data: unknown) => string | null;
  toTable: (data: unknown) => DataTable;
}

function entry<K extends ChartId>(
  module: ChartModule<ChartDataMap[K]> & { id: K },
): ChartRegistryEntry {
  return {
    id: module.id,
    titleKey: module.titleKey,
    empty: module.empty,
    buildOption: (data, ctx) => module.buildOption(data as ChartDataMap[K], ctx),
    emptyReason: (data) => module.emptyReason(data as ChartDataMap[K]),
    toTable: (data) => module.toTable(data as ChartDataMap[K]),
  };
}

export const chartModules = {
  C01: { id: 'C01', titleKey: 'chart.C01.title', empty: C01_EMPTY, ...C01 },
  C02: { id: 'C02', titleKey: 'chart.C02.title', empty: C02_EMPTY, ...C02 },
  C03: { id: 'C03', titleKey: 'chart.C03.title', empty: C03_EMPTY, ...C03 },
  C04: { id: 'C04', titleKey: 'chart.C04.title', empty: C04_EMPTY, ...C04 },
  C05: { id: 'C05', titleKey: 'chart.C05.title', empty: C05_EMPTY, ...C05 },
  C06: { id: 'C06', titleKey: 'chart.C06.title', empty: C06_EMPTY, ...C06 },
  C07: { id: 'C07', titleKey: 'chart.C07.title', empty: C07_EMPTY, ...C07 },
  C08: { id: 'C08', titleKey: 'chart.C08.title', empty: C08_EMPTY, ...C08 },
  C09: { id: 'C09', titleKey: 'chart.C09.title', empty: C09_EMPTY, ...C09 },
  C10: { id: 'C10', titleKey: 'chart.C10.title', empty: C10_EMPTY, ...C10 },
} as const satisfies { [K in ChartId]: ChartModule<ChartDataMap[K]> & { id: K } };

export const chartRegistry: ChartRegistryEntry[] = [
  entry<'C01'>(chartModules.C01),
  entry<'C02'>(chartModules.C02),
  entry<'C03'>(chartModules.C03),
  entry<'C04'>(chartModules.C04),
  entry<'C05'>(chartModules.C05),
  entry<'C06'>(chartModules.C06),
  entry<'C07'>(chartModules.C07),
  entry<'C08'>(chartModules.C08),
  entry<'C09'>(chartModules.C09),
  entry<'C10'>(chartModules.C10),
];
