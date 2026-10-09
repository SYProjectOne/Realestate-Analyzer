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
import { matching, recordRequests } from '../_shared/testing';
import { highlightExcerpt } from './ProvenanceTab';

vi.mock('@/charts/EChartRuntime', () => ({ default: () => null }));
beforeEach(() => resetMockState());

async function exampleDetail(): Promise<ComplexDetail> {
  const res = await getResponse(
    generatedHandlers as RequestHandler[],
    new Request('http://localhost/api/complexes/2'),
  );
  return (await res?.json()) as ComplexDetail;
}

describe('highlightExcerpt', () => {
  it('오프셋이 맞으면 그 위치, 아니면 문자열 검색', () => {
    expect(highlightExcerpt('abcXYZdef', 'XYZ', 3, 6)).toEqual({
      before: 'abc',
      mark: 'XYZ',
      after: 'def',
      searched: false,
    });
    expect(highlightExcerpt('abcXYZdef', 'XYZ', 0, 3)?.searched).toBe(true);
    expect(highlightExcerpt('abc', 'XYZ', 0, 3)).toBeNull();
    expect(highlightExcerpt('abc', null, 0, 3)).toBeNull();
  });
});

describe('G3 단지 상세', () => {
  it('탭은 URL 해시: #payment로 열면 납부 조건 탭, 클릭하면 해시가 바뀐다', async () => {
    const { router } = renderRoute('/complexes/2#payment');
    const tablist = await screen.findByRole('tablist', { name: t('page.G3.tabs') });
    expect(within(tablist).getByRole('tab', { name: t('page.G3.tab.payment') })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    await userEvent.click(within(tablist).getByRole('tab', { name: t('page.G3.tab.ladder') }));
    await waitFor(() => expect(router.state.location.hash).toBe('#ladder'));
    expect(
      screen.getByRole('radiogroup', { name: t('page.G3.ladder.horizons') }),
    ).toBeInTheDocument();
  });

  it('헤더: 접수 배지 · 현재 구매가 범위 · 전매 D-day', async () => {
    renderRoute('/complexes/2');
    await screen.findByRole('tablist', { name: t('page.G3.tabs') });
    expect(screen.getAllByTestId('intake-badge').length).toBeGreaterThan(0);
    expect(screen.getAllByText(t('page.G3.header.price')).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/\(D[-+]\d+\)|D-day/).length).toBeGreaterThan(0);
  });

  it('출처 원문 탭은 열 때만 원문을 받고, 발췌 위치를 <mark>로 강조한다', async () => {
    const rec = recordRequests();
    renderRoute('/complexes/2');
    await screen.findByRole('tablist', { name: t('page.G3.tabs') });
    expect(matching(rec.requests, 'GET', /\/raw\//)).toHaveLength(0);
    await userEvent.click(screen.getByRole('tab', { name: t('page.G3.tab.provenance') }));
    const raw = await screen.findByTestId('raw-text');
    const mark = within(raw).getByLabelText(t('page.G3.provenance.highlight'));
    expect(mark.tagName).toBe('MARK');
    expect(mark.textContent).toBeTruthy();
    expect(raw.textContent).toContain(mark.textContent ?? '');
    expect(matching(rec.requests, 'GET', /\/raw\//).length).toBeGreaterThan(0);
    rec.stop();
  });

  it('판정기 로그: review/escaped 봉투는 회색 + "미해결", 캐시 배지', async () => {
    const detail = await exampleDetail();
    const base = detail.judgments[0] ?? {
      tool: 'noul',
      purpose: 'x',
      input_hash: 'sha256:x',
      status: 'ok',
      confidence: 0.9,
      cached: false,
      result: {},
      raw: {},
      duration_ms: 10,
      judgment_seq: 1,
      created_at: '2026-10-07T00:00:00+09:00',
    };
    server.use(
      http.get(mswPath('/complexes/:id'), () =>
        HttpResponse.json({
          ...detail,
          judgments: [
            { ...base, status: 'ok', cached: true, judgment_seq: 901 },
            { ...base, status: 'review', cached: false, judgment_seq: 902 },
            { ...base, status: 'escaped', cached: false, judgment_seq: 903 },
          ],
        }),
      ),
    );
    renderRoute('/complexes/2#judgments');
    const rows = await screen.findAllByRole('row');
    const unresolved = rows.filter((r) => r.dataset.unresolved === 'true');
    expect(unresolved).toHaveLength(2);
    for (const row of unresolved) {
      expect(row).toHaveClass('text-grayed');
      expect(within(row).getByText(t('page.common.unresolved'))).toBeInTheDocument();
    }
    expect(screen.getAllByTestId('cached-badge')).toHaveLength(1);
  });
});
