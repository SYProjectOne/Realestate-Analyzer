/**
 * R3c(3차 리뷰) 화면 항목:
 *  - delta_rerank(이전 run 대비 rerank 점수 차) 표시: G1 TOP 5 · G4 비교 · G5 이전 대비 표
 *  - G6 실거래 건수는 FactCell(집계 사실과 같은 출처·라벨) — 라벨 없는 숫자 금지
 *  - 사실이 아닌 숫자는 비수치 메타(data-meta)로만 보인다
 */
import { render, screen, within } from '@testing-library/react';
import { getResponse, http, HttpResponse, type RequestHandler } from 'msw';
import type { Dashboard, Market, ScoreRow } from '@/api/types';
import dashboardExample from '../../../contracts/examples/dashboard_b.json';
import { MetaText, MetaValue } from '@/components';
import { t } from '@/i18n';
import { metaNumber, metaText } from '@/lib/meta';
import { generatedHandlers } from '@/mocks/handlers.gen';
import { resetMockState } from '@/mocks/handlers.extra';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { renderRoute } from '@/test/render';
import './_shared/testing';
import { DiffTable } from './scenario';

vi.mock('@/charts/EChartRuntime', () => ({ default: () => null }));
beforeEach(() => resetMockState());

const top5 = (dashboardExample as unknown as { value: Dashboard }).value.top5 as ScoreRow[];

describe('delta_rerank 표시 (3차 리뷰 하위 점검)', () => {
  it('G1 TOP 5 카드: delta_rerank 가 있는 단지는 "rerank 변화" + 라벨 배지', async () => {
    renderRoute('/?scenario=B');
    const list = await screen.findByRole('list', { name: t('page.G1.top5') });
    const cells = await within(list).findAllByTestId('top5-delta-rerank');
    const withDelta = top5.filter((r) => r.delta_rerank);
    expect(withDelta.length).toBeGreaterThan(0);
    expect(cells.length).toBeGreaterThan(0);
    for (const cell of cells) {
      // FactCell = 값 + 라벨 배지(출처 버튼)
      expect(cell.querySelector('[data-prov]')).not.toBeNull();
      expect(within(cell).getByTestId('label-badge')).toBeInTheDocument();
    }
    expect(within(list).getAllByText(t('page.common.deltaRerank')).length).toBe(cells.length);
  });

  it('G4 비교 표: rerank 변화 행(열 = 단지), 없으면 "확인 불가(이전 run 없음)"', async () => {
    renderRoute('/compare?ids=2,7,4&scenario=B');
    const grid = await screen.findByRole('table', { name: t('page.G4.grid') });
    const row = within(grid).getByTestId('compare-delta-rerank');
    expect(within(row).getByText(t('page.common.deltaRerank'))).toBeInTheDocument();
    expect(within(row).getAllByRole('cell')).toHaveLength(3);
  });

  it('G5 이전 대비 표: 새 run 의 delta_rerank 열', () => {
    const after = top5.slice(0, 3);
    const before = top5.slice(0, 3).map((r) => ({ ...r, delta_rerank: null }));
    render(<DiffTable before={before} after={after} />);
    expect(
      screen.getByRole('columnheader', { name: t('page.G5.diffCol.deltaRerank') }),
    ).toBeInTheDocument();
    const cells = screen.getAllByTestId('diff-delta-rerank');
    expect(cells).toHaveLength(3);
    after.forEach((row, i) => {
      const cell = cells[i] as HTMLElement;
      if (row.delta_rerank && row.delta_rerank.v !== null) {
        expect(within(cell).getByTestId('label-badge')).toBeInTheDocument();
      } else {
        expect(cell).toHaveTextContent(t('page.common.deltaRerankNone'));
      }
    });
  });
});

describe('G6 실거래 건수 = FactCell (FactCell 밖 숫자 금지)', () => {
  it('생활권 시세 표의 건수 열은 라벨 배지를 가진다', async () => {
    server.use(
      http.get(mswPath('/snapshots/:sid/market'), async ({ request }) => {
        const res = await getResponse(generatedHandlers as RequestHandler[], request.clone());
        const market = (await res?.json()) as Market;
        const base = {
          v: 512_000_000,
          label: '확인됨' as const,
          prov: 'cs_1',
          checked_at: '2026-10-08',
          unit: 'won' as const,
        };
        // 계약 .10: n_trades = 서버 Fact(라벨 = 그 실거래 행들의 가장 약한 라벨) — 화면은 그대로 보인다
        const count = (v: number, label: '확인됨' | '추정', prov: string) => ({
          v,
          label,
          prov,
          checked_at: '2026-10-08',
          unit: 'count' as const,
          reason: label === '확인됨' ? null : '표본에 추정 행 포함',
        });
        market.living_area_prices = [
          {
            living_area: 'A',
            name: '생활권 A',
            median_won: base,
            low_won: base,
            high_won: base,
            n_trades: count(12, '확인됨', 'cs_1'),
            trade_window: '2026-04~2026-09',
            basis: null,
          },
          {
            living_area: 'B',
            name: '생활권 B',
            median_won: { ...base, label: '확인됨' as const },
            low_won: base,
            high_won: base,
            n_trades: count(5, '추정', 'cs_2'),
            trade_window: '2026-04~2026-09',
            basis: null,
          },
        ];
        return HttpResponse.json(market);
      }),
    );
    renderRoute('/market');
    const table = await screen.findByRole('table', { name: t('page.G6.prices') });
    const row = within(table).getAllByRole('row')[1] as HTMLElement;
    const nCell = within(row).getAllByRole('cell')[3] as HTMLElement;
    expect(nCell).toHaveTextContent('12');
    expect(within(nCell).getByTestId('label-badge')).toHaveTextContent('확인됨');
    expect(nCell.querySelector('[data-prov="cs_1"]')).not.toBeNull();
    // 중앙값이 확인됨이어도 건수 라벨은 서버 n_trades Fact 의 것(화면이 만들지 않는다)
    const row2 = within(table).getAllByRole('row')[2] as HTMLElement;
    const nCell2 = within(row2).getAllByRole('cell')[3] as HTMLElement;
    expect(nCell2).toHaveTextContent('5');
    expect(within(nCell2).getByTestId('label-badge')).toHaveTextContent('추정');
    expect(nCell2.querySelector('[data-prov="cs_2"]')).not.toBeNull();
  });
});

describe('비수치 메타(MetaValue·MetaText·metaText)', () => {
  it('data-meta 로 종류를 남기고 lib/format 과 같은 문자열', () => {
    render(
      <div>
        <MetaValue kind="count" value={1234} />
        <MetaValue kind="rank" value={3} as="rank" />
        <MetaValue kind="status" value={403} as="plain" />
        <MetaValue kind="input" value={0.355} as="number" digits={2} />
        <MetaText kind="count" k="page.G2.trayCount" params={{ n: 4 }} />
      </div>,
    );
    expect(screen.getByText('1,234')).toHaveAttribute('data-meta', 'count');
    expect(screen.getByText(t('unit.rank', { rank: 3 }))).toHaveAttribute('data-meta', 'rank');
    expect(screen.getByText('403')).toHaveAttribute('data-meta', 'status');
    expect(screen.getByText('0.36')).toHaveAttribute('data-meta', 'input');
    expect(screen.getByText(t('page.G2.trayCount', { n: '4' }))).toHaveAttribute(
      'data-meta',
      'count',
    );
  });

  it('metaNumber·metaText: 정수 → 천 단위, 소수 → 둘째 자리, 신뢰도', () => {
    expect(metaNumber(12345)).toBe('12,345');
    expect(metaNumber(1.5)).toBe('1.50');
    expect(metaNumber({ n: 0.48, as: 'confidence' })).toBe('0.48');
    expect(metaNumber({ n: 1200, as: 'plain' })).toBe('1200');
    expect(metaText('page.G2.count', { shown: 50, total: 1200 })).toBe(
      t('page.G2.count', { shown: '50', total: '1,200' }),
    );
  });

  it('G1 KPI 데이터 신선도 보조 문구(실패·지연 소스 수)는 비수치 메타', async () => {
    renderRoute('/');
    const kpis = await screen.findByRole('list', { name: t('page.G1.kpis') });
    const freshness = kpis.querySelector('[data-kpi="freshness"]') as HTMLElement;
    expect(freshness.querySelector('[data-meta="count"]')).not.toBeNull();
  });
});
