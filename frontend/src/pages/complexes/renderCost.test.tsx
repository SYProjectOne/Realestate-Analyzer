/**
 * R3g FE6 — T16(D10-8) 렌더 비용. 7차 리뷰: T16 p95 33.3ms(기준 34ms 까지 0.7ms). 원인 = 스크롤 프레임마다 G2 표가
 * 다시 그려질 때 창 안의 **모든** 행·셀(FactCell 수백 개)을 다시 렌더하고, 숫자 셀마다 `Intl.NumberFormat` 을 새로 만들었다.
 *  - 행·머리줄은 memo: 행 데이터·선택·열이 같으면 다시 그리지 않는다(정렬 표시만 바뀌면 머리줄만).
 *  - 숫자 포맷터는 자릿수별로 한 번만 만든다.
 */
import { render } from '@testing-library/react';
import { getResponse, type RequestHandler } from 'msw';
import type { ReactElement } from 'react';
import { MemoryRouter } from 'react-router';
import type { ComplexRow, ComplexRowPage } from '@/api/types';
import { formatNumber, formatWon } from '@/lib/format';
import { generatedHandlers } from '@/mocks/handlers.gen';
import type * as Components from '@/components';

const counter = vi.hoisted(() => ({ factCells: 0 }));

vi.mock('@/components', async (importOriginal) => {
  const mod = await importOriginal<typeof Components>();
  const Real = mod.FactCell;
  return {
    ...mod,
    FactCell: (props: Parameters<typeof Real>[0]) => {
      counter.factCells += 1;
      return Real(props);
    },
  };
});

const { ComplexTable } = await import('./ComplexTable');

async function rows(): Promise<ComplexRow[]> {
  const res = await getResponse(
    generatedHandlers as RequestHandler[],
    new Request('http://localhost/api/snapshots/12/complexes?page=1&size=50'),
  );
  return ((await res!.json()) as ComplexRowPage).items;
}

function table(items: ComplexRow[], sort: string): ReactElement {
  return (
    <MemoryRouter>
      <ComplexTable
        rows={items}
        total={items.length}
        asof="2026-10-08"
        sort={sort}
        onSort={() => undefined}
        selected={EMPTY}
        onToggle={TOGGLE}
        maxSelected={6}
        readOnly={false}
        linkSearch=""
      />
    </MemoryRouter>
  );
}
const EMPTY: ReadonlySet<number> = new Set();
const TOGGLE = () => undefined;

describe('T16 렌더 비용: G2 표', () => {
  it('정렬 표시만 바뀌어 표가 다시 그려져도 행(FactCell)은 다시 렌더하지 않는다', async () => {
    const items = await rows();
    expect(items.length).toBeGreaterThan(0);
    counter.factCells = 0;
    const view = render(table(items, 'name'));
    const first = counter.factCells;
    expect(first).toBeGreaterThan(0);
    view.rerender(table(items, '-total'));
    expect(counter.factCells).toBe(first);
  });

  it('숫자 포맷터(Intl.NumberFormat)는 자릿수마다 한 번만 만든다', () => {
    const Real = Intl.NumberFormat;
    let made = 0;
    const counting = function (...args: ConstructorParameters<typeof Real>) {
      made += 1;
      return new Real(...args);
    } as unknown as typeof Intl.NumberFormat;
    Intl.NumberFormat = counting;
    try {
      // 다른 테스트가 아직 만들지 않은 자릿수(3·4)
      for (let i = 0; i < 200; i += 1) {
        formatNumber(i * 1234.5, 3);
        formatNumber(i * 12.5, 4);
        formatWon(i * 12_345_678);
      }
    } finally {
      Intl.NumberFormat = Real;
    }
    expect(made).toBeLessThanOrEqual(3);
  });
});
