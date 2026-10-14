/**
 * R9-UI 사용자 피드백(민감도 C10): 성분 내부 키(p10·rerank·gap·benchmark·supply·liquidity·move_in)가 화면 글자로
 * 나오지 않는다 — 차트 축·범례·계열 이름·표·문구 어디에도. 쉬운 말(ko.json 성분 이름)로만 보인다.
 */
import { screen, within } from '@testing-library/react';
import ko from '@/i18n/ko.json';
import { t } from '@/i18n';
import { renderRoute, renderWithProviders } from '@/test/render';
import { resetMockState } from '@/mocks/handlers.extra';
import { compare, dashboard, sensitivity, stableSensitivity } from './gallery/fixtures';
import * as C06 from './C06/buildOption';
import * as C10 from './C10/buildOption';
import { C10Sensitivity } from './C10';

vi.mock('@/charts/EChartRuntime', () => ({ default: () => null }));
beforeEach(() => resetMockState());

export const RAW_KEY = /\b(p10|rerank|gap|benchmark|supply|liquidity|move_in)\b/;

/** 옵션에서 사용자에게 보이는 글자(축 data·범례·계열 이름·제목)만 모은다 */
function visibleOptionText(option: Record<string, unknown>): string[] {
  const out: string[] = [];
  const axes = (v: unknown) => (Array.isArray(v) ? v : v ? [v] : []) as Record<string, unknown>[];
  for (const axis of [...axes(option.xAxis), ...axes(option.yAxis)]) {
    if (Array.isArray(axis.data)) out.push(...axis.data.map(String));
  }
  for (const legend of axes(option.legend)) {
    if (Array.isArray(legend.data)) out.push(...legend.data.map(String));
  }
  for (const series of axes(option.series)) {
    if (typeof series.name === 'string') out.push(series.name);
  }
  return out;
}

function tableText(table: { columns: { header: string }[]; rows: Record<string, unknown>[] }) {
  return [
    ...table.columns.map((c) => c.header),
    ...table.rows.flatMap((r) =>
      Object.values(r).filter((v): v is string => typeof v === 'string'),
    ),
  ];
}

describe('성분 내부 키가 화면 글자로 나오지 않는다', () => {
  it('ko.json 문구 어디에도 없다', () => {
    const hits: string[] = [];
    (function walk(node: unknown, path: string[]) {
      if (typeof node === 'string') {
        if (RAW_KEY.test(node)) hits.push(`${path.join('.')}: ${node}`);
        return;
      }
      if (node && typeof node === 'object') {
        for (const [k, v] of Object.entries(node)) walk(v, [...path, k]);
      }
    })(ko, []);
    expect(hits).toEqual([]);
  });

  it('C10 민감도: x축·표 행 이름은 쉬운 말("… 비중 +10%p")', () => {
    const data = { sensitivity: sensitivity(), names: { '1': 'A' } };
    const option = C10.buildOption(data) as Record<string, unknown>;
    const text = [...visibleOptionText(option), ...tableText(C10.toTable(data))];
    expect(text.filter((x) => RAW_KEY.test(x))).toEqual([]);
    const first = sensitivity().cells[0];
    expect(first).toBeDefined();
    expect(C10.variantLabel(first!)).toBe(
      t('chart.C10.variantLabel', {
        component: t('chart.C06.component.p10'),
        sign: '+',
        pp: '10',
      }),
    );
  });

  it('C06 점수 분해: 축·범례·표', () => {
    const d = dashboard();
    const data = { rows: d.top5, weights: d.weights, orientation: 'vertical' as const };
    const option = C06.buildOption(data) as Record<string, unknown>;
    const text = [...visibleOptionText(option), ...tableText(C06.toTable(data))];
    expect(text.filter((x) => RAW_KEY.test(x))).toEqual([]);
  });

  it('C10 패널: 한 문장 설명 · 비중/민감도 ⓘ · 순위 변동 없음/있음 · 배지 쉬운 말 · 순위 머리 줄바꿈 없음', () => {
    const { container } = renderWithProviders(
      <C10Sensitivity data={{ sensitivity: stableSensitivity(), names: {} }} />,
    );
    expect(screen.getByText(t('chart.C10.explain'))).toBeInTheDocument();
    const terms = [...container.querySelectorAll('[data-testid="term"]')].map((el) =>
      el.getAttribute('data-term'),
    );
    expect(terms).toEqual(expect.arrayContaining(['weight', 'sensitivity']));
    expect(screen.getByTestId('stable-badge')).toHaveTextContent(t('chart.C10.stable'));
    const table = container.querySelector('table') as HTMLElement;
    expect(within(table).getByText(t('chart.C10.changedCol'))).toBeInTheDocument();
    const values = [...table.querySelectorAll('tbody tr td:last-child')].map(
      (td) => td.textContent,
    );
    for (const v of values)
      expect(v).toMatch(new RegExp(`^(${t('chart.C10.changedNo')}|${t('chart.C10.changedYes')})`));
    for (const th of table.querySelectorAll('thead th')) {
      expect(th.className).toContain('whitespace-nowrap');
    }
    expect(container.textContent ?? '').not.toMatch(RAW_KEY);
  });

  it('G4 화면 글자 전체에 내부 키가 없다', async () => {
    expect(compare().rows.length).toBeGreaterThan(1);
    renderRoute('/compare?ids=2,7,4');
    await screen.findByRole('table', { name: t('page.G4.grid') });
    expect(document.body.textContent ?? '').not.toMatch(RAW_KEY);
  });
});
