/**
 * C2 표시(계약 2026-10-09.4, D9-1): 판정 범위 5값 — 판정 대상·보류·참고·미해결·제외.
 * 표시 문구: 보류 → '보류 — 공고 후 재판정', 참고 → '참고 후보(순위만)', 미해결 → '미해결(분류 판정 미해결)'.
 */
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { getResponse, http, HttpResponse, type RequestHandler } from 'msw';
import type { ComplexDetail, ComplexRowPage, JudgeScope } from '@/api/types';
import { JUDGE_SCOPES } from '@/api/types';
import { t } from '@/i18n';
import { resetMockState } from '@/mocks/handlers.extra';
import { generatedHandlers } from '@/mocks/handlers.gen';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { renderRoute } from '@/test/render';
import { enumText } from './_shared';
import { matching, recordRequests } from './_shared/testing';

vi.mock('echarts-for-react', () => ({ default: () => null }));
beforeEach(() => resetMockState());

async function example<T>(request: Request): Promise<T> {
  const res = await getResponse(generatedHandlers as RequestHandler[], request.clone());
  return (await res?.json()) as T;
}

describe('C2 판정 범위 표시', () => {
  it('ko.json 표시 문구: 보류·참고·미해결', () => {
    expect(JUDGE_SCOPES).toEqual(['판정 대상', '보류', '참고', '미해결', '제외']);
    expect(enumText('page.common.judgeScope', '미해결')).toBe('미해결(분류 판정 미해결)');
    expect(enumText('page.common.judgeScope', '참고')).toBe('참고 후보(순위만)');
    expect(enumText('page.common.judgeScope', '보류')).toBe('보류 — 공고 후 재판정');
  });

  it('G2 필터에 미해결 포함 → filter[judge_scope]=미해결', async () => {
    const rec = recordRequests();
    const { router } = renderRoute('/complexes');
    await screen.findByRole('table', { name: t('page.G2.table') });
    const filters = screen.getByRole('search', { name: t('page.G2.filters') });
    const select = within(filters).getByLabelText(t('page.G2.filter.judge_scope'));
    const labels = Array.from(select.querySelectorAll('option')).map((o) => o.textContent);
    for (const scope of JUDGE_SCOPES) {
      expect(labels).toContain(enumText('page.common.judgeScope', scope));
    }
    await userEvent.selectOptions(select, '미해결');
    await waitFor(() => expect(router.state.location.search).toContain('judge_scope='));
    await waitFor(() => {
      const calls = matching(rec.requests, 'GET', /\/snapshots\/\d+\/complexes$/);
      expect(calls.some((c) => c.url.searchParams.get('filter[judge_scope]') === '미해결')).toBe(
        true,
      );
    });
    rec.stop();
  });

  it('G2 표: 판정 대상이 아닌 행에 범위 배지(미해결·참고·보류 표시 문구)', async () => {
    const scopes: JudgeScope[] = ['미해결', '참고', '보류', '판정 대상'];
    server.use(
      http.get(mswPath('/snapshots/:sid/complexes'), async ({ request }) => {
        const page = await example<ComplexRowPage>(request);
        const items = page.items.slice(0, scopes.length).map((row, i) => ({
          ...row,
          judge_scope: scopes[i] as JudgeScope,
        }));
        return HttpResponse.json({ ...page, items, total: items.length });
      }),
    );
    renderRoute('/complexes');
    const table = await screen.findByRole('table', { name: t('page.G2.table') });
    await waitFor(() => expect(within(table).getAllByTestId('judge-scope')).toHaveLength(3));
    const badges = within(table)
      .getAllByTestId('judge-scope')
      .map((b) => b.textContent);
    expect(badges).toEqual([
      '미해결(분류 판정 미해결)',
      '참고 후보(순위만)',
      '보류 — 공고 후 재판정',
    ]);
  });

  it('G3 헤더: 점수 행의 판정 범위 배지(미해결)', async () => {
    server.use(
      http.get(mswPath('/complexes/:id'), async ({ request }) => {
        const detail = await example<ComplexDetail>(request);
        return HttpResponse.json({
          ...detail,
          score: detail.score ? { ...detail.score, judge_scope: '미해결' } : detail.score,
        });
      }),
    );
    renderRoute('/complexes/2');
    const badge = await screen.findByTestId('judge-scope');
    expect(badge).toHaveTextContent('미해결(분류 판정 미해결)');
  });
});
