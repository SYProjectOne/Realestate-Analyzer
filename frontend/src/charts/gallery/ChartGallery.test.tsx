import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '@/test/render';
import { CHART_IDS } from '../types';
import { ChartGallery, GALLERY_CASES } from './ChartGallery';

// jsdom에는 canvas가 없다 — ECharts 렌더는 Playwright(tests/e2e/charts-gallery.spec.ts)가 본다
vi.mock('../EChart', () => ({
  EChart: ({ ariaLabel }: { ariaLabel: string }) => (
    <div data-testid="echart" role="img" aria-label={ariaLabel} />
  ),
}));

describe('ChartGallery (차트 10개 × 정상/빈/특수)', () => {
  it('차트마다 정상·빈·특수 상태가 하나 이상 있다', () => {
    for (const id of CHART_IDS) {
      const states = GALLERY_CASES.filter((c) => c.chart === id).map((c) => c.state);
      expect(states).toEqual(expect.arrayContaining(['normal', 'empty', 'special']));
    }
  });

  it('빈 상태 카드는 차트 대신 빈 상태 문구를 보여 준다', () => {
    renderWithProviders(<ChartGallery />);
    const expected: Record<string, string> = {
      C01: '사다리 판정 없음',
      C02: '비교군 없음(분양가 미공개 — 공고 후 재판정)',
      C03: '벤치마크 없음',
      C04: '입주 물량 없음',
      C05: '미분양 자료 없음',
      C06: '점수 없음',
      C07: '판정 없음',
      C08: '본청약만',
      C09: '호재 없음',
      C10: '민감도 없음',
    };
    for (const [id, text] of Object.entries(expected)) {
      const card = screen.getByTestId(`gallery-${id}-empty`);
      expect(within(card).getByRole('status')).toHaveTextContent(text);
    }
  });

  it('특수 상태 배지: 미해결·표본·미판정·동률·질문·순위 불안정', () => {
    renderWithProviders(<ChartGallery />);
    expect(
      within(screen.getByTestId('gallery-C01-special')).getAllByText('미해결').length,
    ).toBeGreaterThan(0);
    expect(
      within(screen.getByTestId('gallery-C03-special')).getByText('표본 2, 추정'),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId('gallery-C06-special')).getByText('미판정'),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId('gallery-C07-special')).getByText('동률(신뢰도 0.48)'),
    ).toBeInTheDocument();
    expect(within(screen.getByTestId('gallery-C07-escaped')).getByRole('status')).toHaveTextContent(
      '질문 남김',
    );
    expect(
      within(screen.getByTestId('gallery-C10-normal')).getByText('순위 불안정'),
    ).toBeInTheDocument();
  });

  it('정상 상태 카드는 라벨 배지(텍스트)를 단다', () => {
    renderWithProviders(<ChartGallery />);
    const card = screen.getByTestId('gallery-C02-normal');
    expect(within(card).getAllByTestId('label-badge').length).toBeGreaterThan(0);
  });

  it('표로 보기 → Fact 셀 클릭이 출처 패널로 이어진다', async () => {
    renderWithProviders(<ChartGallery />);
    const card = screen.getByTestId('gallery-C02-normal');
    await userEvent.click(within(card).getByRole('button', { name: '표로 보기' }));
    const table = within(card).getByRole('table');
    const cells = within(table).getAllByRole('button');
    await userEvent.click(cells[0]!);
    expect(await screen.findByRole('dialog', { name: '출처' })).toBeInTheDocument();
  });
});
