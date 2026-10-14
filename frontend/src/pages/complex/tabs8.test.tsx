/**
 * R9-UI P8(30-proposal §9, D28-3): G3 탭 7개(판정 기록은 근거 원문 안 접힌 구획), 경쟁률 표 위로, 미달 표기,
 * 가격 갭 부호 문장, 필수 옵션 고지문 각주. 해시 키(#judgments 등)는 그대로.
 */
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { getResponse, http, HttpResponse, type RequestHandler } from 'msw';
import type { ComplexDetail } from '@/api/types';
import { t } from '@/i18n';
import { generatedHandlers } from '@/mocks/handlers.gen';
import { resetMockState } from '@/mocks/handlers.extra';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { renderRoute } from '@/test/render';

vi.mock('@/charts/EChartRuntime', () => ({ default: () => null }));
beforeEach(() => resetMockState());

async function exampleDetail(): Promise<ComplexDetail> {
  const res = await getResponse(
    generatedHandlers as RequestHandler[],
    new Request('http://localhost/api/complexes/2'),
  );
  return (await res?.json()) as ComplexDetail;
}

function useDetail(detail: ComplexDetail) {
  server.use(http.get(mswPath('/complexes/:id'), () => HttpResponse.json(detail)));
}

describe('R9-UI P8 G3 탭', () => {
  it('탭 7개(쉬운 이름, 주변 시세 비교가 가격 전망 앞)', async () => {
    renderRoute('/complexes/2');
    const tabs = await screen.findAllByRole('tab');
    expect(tabs.map((tab) => tab.textContent)).toEqual([
      t('page.G3.tab.price'),
      t('page.G3.tab.payment'),
      t('page.G3.tab.events'),
      t('page.G3.tab.gap'),
      t('page.G3.tab.ladder'),
      t('page.G3.tab.catalysts'),
      t('page.G3.tab.provenance'),
    ]);
  });

  it('#judgments 로 열면 근거 원문 탭 + 판정 기록 구획이 펼쳐진다(링크 경로 1클릭 그대로)', async () => {
    renderRoute('/complexes/2#judgments');
    const tab = await screen.findByRole('tab', { name: t('page.G3.tab.provenance') });
    expect(tab).toHaveAttribute('aria-selected', 'true');
    const block = await screen.findByTestId('judgments-block');
    expect(block).toHaveAttribute('open');
    expect(within(block).getByText(t('page.G3.tab.judgments'))).toBeInTheDocument();
  });

  it('근거 원문 탭을 그냥 열면 판정 기록은 접혀 있다(2클릭, D28-3)', async () => {
    renderRoute('/complexes/2#provenance');
    const block = await screen.findByTestId('judgments-block');
    expect(block).not.toHaveAttribute('open');
  });

  it('호재 0건이면 탭 이름 옆 "(0)" — 빈 탭은 지우지 않는다', async () => {
    const detail = await exampleDetail();
    useDetail({ ...detail, catalysts: [] });
    renderRoute('/complexes/2');
    expect(
      await screen.findByRole('tab', {
        name: t('page.G3.tab.countZero', { name: t('page.G3.tab.catalysts') }),
      }),
    ).toBeInTheDocument();
  });

  it('경쟁률 표가 차트보다 앞, 미달 표기 "△307" → "미달 307세대"(원문은 title)', async () => {
    const detail = await exampleDetail();
    const first = detail.competition[0];
    expect(first).toBeDefined();
    useDetail({
      ...detail,
      competition: [
        { ...first!, ratio_or_shortfall_text: '(△307)' },
        ...detail.competition.slice(1),
      ],
    });
    renderRoute('/complexes/2#events');
    const section = await screen.findByRole('region', { name: t('page.G3.competition.title') });
    const chart = await screen.findByText(t('chart.C08.title'));
    expect(section.compareDocumentPosition(chart) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(within(section).getByText(t('page.G3.competition.ratio'))).toBeInTheDocument();
    const cell = within(section).getByText(t('page.G3.competition.shortfall', { n: '307' }));
    expect(cell).toHaveAttribute('title', '(△307)');
    expect(within(section).getByText(t('page.G3.competition.pointsMissing'))).toBeInTheDocument();
  });

  it('주변 시세 비교: 가격 갭 부호 문장 1번 + 비교 기준 + 점수는 "가격 갭 점수(0~10)"', async () => {
    const detail = await exampleDetail();
    renderRoute('/complexes/2#gap');
    const panel = await screen.findByRole('tabpanel');
    expect(within(panel).getAllByText(t('page.G3.gap.meaning'))).toHaveLength(1);
    expect(within(panel).getByText(t('page.G3.gap.basis'))).toBeInTheDocument();
    expect(within(panel).getByText(t('page.G3.gap.score'))).toBeInTheDocument();
    expect(panel.querySelector(`[data-prov="${detail.gap.gap_pct.prov}"]`)).not.toBeNull();
  });

  it('가격 전망 탭: 정의 한 줄 "당첨 확률이 아닙니다"', async () => {
    renderRoute('/complexes/2#ladder');
    const panel = await screen.findByRole('tabpanel');
    expect(within(panel).getByText(t('page.G3.ladder.note'))).toBeInTheDocument();
  });

  it('필수 옵션 칸의 같은 고지문은 표 아래 각주 1번 + 칸마다 ①', async () => {
    const detail = await exampleDetail();
    const notice = '상기 공급금액에는 발코니 확장비용 및 추가 선택품목이 포함되지 않았습니다';
    useDetail({ ...detail, types: detail.types.map((r) => ({ ...r, options_text: notice })) });
    renderRoute('/complexes/2#price');
    const panel = await screen.findByRole('tabpanel');
    await waitFor(() => expect(within(panel).getAllByText(notice)).toHaveLength(1));
    expect(within(panel).getByTestId('options-footnote')).toHaveTextContent(notice);
    expect(within(panel).getAllByTestId('options-ref')).toHaveLength(detail.types.length);
  });

  it('탭 클릭은 해시를 바꾼다(키 불변)', async () => {
    const { router } = renderRoute('/complexes/2');
    await userEvent.click(await screen.findByRole('tab', { name: t('page.G3.tab.gap') }));
    expect(router.state.location.hash).toBe('#gap');
  });
});
