/**
 * D10-1(계약 2026-10-09.6 rejudge_needed): 화면의 범위·순위·총점은 그 스냅샷 score_run **저장값**.
 * 현재 사실로 계산한 범위가 저장값과 다르면 '재판정 필요' 배지 + rejudge 잡 제안만(저장값·현재값을 섞지 않는다).
 * N-M3(D9-2): 벤치마크 행이 없으면 G1 에 '벤치마크 없음(<reason>)' — 종합 점수 미계산 이유.
 */
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { getResponse, http, HttpResponse, type RequestHandler } from 'msw';
import { ROLE_STORAGE_KEY, TOKEN_STORAGE_KEY } from '@/api/auth';
import type { CompareView, ComplexDetail, ComplexRowPage, Dashboard } from '@/api/types';
import { t } from '@/i18n';
import { resetMockState } from '@/mocks/handlers.extra';
import { generatedHandlers } from '@/mocks/handlers.gen';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { renderRoute } from '@/test/render';
import { matching, recordRequests } from './_shared/testing';

vi.mock('@/charts/EChartRuntime', () => ({ default: () => null }));
beforeEach(() => resetMockState());

async function example<T>(request: Request): Promise<T> {
  const res = await getResponse(generatedHandlers as RequestHandler[], request.clone());
  return (await res?.json()) as T;
}

function patchDashboard(fn: (d: Dashboard) => Dashboard) {
  server.use(
    http.get(mswPath('/snapshots/:sid/dashboard'), async ({ request }) =>
      HttpResponse.json(fn(await example<Dashboard>(request))),
    ),
  );
}

/** top5 중 앞의 n개 행만 rejudge_needed, 대시보드도 true */
function flagTop(n: number) {
  patchDashboard((d) => ({
    ...d,
    rejudge_needed: true,
    top5: d.top5.map((row, i) => ({ ...row, rejudge_needed: i < n })),
  }));
}

describe('D10-1 G1 재판정 필요', () => {
  it('rejudge_needed 행의 TOP 5 카드에 "재판정 필요" 배지(저장 순위는 그대로)', async () => {
    flagTop(1);
    renderRoute('/');
    const top5 = await screen.findByRole('list', { name: t('page.G1.top5') });
    const cards = within(top5).getAllByRole('listitem');
    await waitFor(() => expect(within(top5).getAllByTestId('rejudge-needed')).toHaveLength(1));
    const first = cards[0] as HTMLElement;
    expect(within(first).getByTestId('rejudge-needed')).toHaveTextContent(
      t('page.common.rejudgeNeeded'),
    );
    expect(within(cards[1] as HTMLElement).queryByTestId('rejudge-needed')).toBeNull();
  });

  it('전역 안내 + 재판정 잡 등록 → POST /jobs rejudge {snapshot_id, scenario_id:null, complex_ids, reason} → 진행', async () => {
    flagTop(2);
    const rec = recordRequests();
    renderRoute('/');
    const notice = await screen.findByTestId('rejudge-notice');
    expect(notice).toHaveTextContent(t('page.G1.rejudgeNotice'));
    const top5 = await screen.findByRole('list', { name: t('page.G1.top5') });
    const ids = within(top5)
      .getAllByRole('listitem')
      .slice(0, 2)
      .map((li) => Number((li as HTMLElement).dataset.complexId));
    const button = within(notice).getByRole('button', { name: t('page.G1.rejudgeRun') });
    expect(button).toHaveAttribute('data-write');
    await userEvent.click(button);
    await waitFor(() => expect(matching(rec.requests, 'POST', '/jobs')).toHaveLength(1));
    const body = (await matching(rec.requests, 'POST', '/jobs')[0]?.body) as Record<
      string,
      unknown
    >;
    expect(body).toEqual({
      job_name: 'rejudge',
      payload: {
        snapshot_id: expect.any(Number),
        scenario_id: null,
        complex_ids: ids,
        reason: '재판정 필요(저장 범위 ≠ 현재 범위)',
      },
    });
    expect(await within(notice).findByText(t('job.name.rejudge'))).toBeInTheDocument();
    rec.stop();
  });

  it('대시보드만 true(TOP 5 행은 모두 false) → complex_ids=null', async () => {
    patchDashboard((d) => ({ ...d, rejudge_needed: true }));
    const rec = recordRequests();
    renderRoute('/');
    const notice = await screen.findByTestId('rejudge-notice');
    await userEvent.click(within(notice).getByRole('button', { name: t('page.G1.rejudgeRun') }));
    await waitFor(() => expect(matching(rec.requests, 'POST', '/jobs')).toHaveLength(1));
    const body = (await matching(rec.requests, 'POST', '/jobs')[0]?.body) as {
      payload: Record<string, unknown>;
    };
    expect(body.payload.complex_ids).toBeNull();
    rec.stop();
  });

  it('읽기 전용 토큰이면 재판정 버튼이 꺼진다(안내는 보인다)', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-read');
    window.localStorage.setItem(ROLE_STORAGE_KEY, 'read');
    flagTop(1);
    renderRoute('/');
    const notice = await screen.findByTestId('rejudge-notice');
    const button = within(notice).getByRole('button', { name: t('page.G1.rejudgeRun') });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute('title', t('auth.readOnlyHint'));
  });

  it('rejudge_needed=false(계약 예시) → 안내·배지 없음', async () => {
    renderRoute('/');
    await screen.findByRole('list', { name: t('page.G1.top5') });
    expect(screen.queryByTestId('rejudge-notice')).toBeNull();
    expect(screen.queryByTestId('rejudge-needed')).toBeNull();
  });
});

describe('N-M3 G1 벤치마크 없음', () => {
  it('benchmark_absence → "벤치마크 없음(<reason>)" + 종합 미계산 설명', async () => {
    const reason = '입주 후 실거래가 있는 과거 분양 사례 없음(생활권·지역 전체 표본 0)';
    patchDashboard((d) => ({ ...d, benchmark_absence: { code: 'no_sample', reason } }));
    renderRoute('/');
    const notice = await screen.findByTestId('benchmark-absence');
    // R11 SH-8: '근처 새 아파트 실적 없음(<서버 사유>)' + 종합 점수 미계산 설명
    expect(notice).toHaveTextContent(t('page.G1.benchmarkAbsentBadge', { reason }));
    expect(notice).toHaveTextContent(t('page.G1.benchmarkAbsentHint'));
    expect(notice).toHaveAttribute('data-code', 'no_sample');
  });

  it('benchmark_absence=null → 표시 없음', async () => {
    renderRoute('/');
    await screen.findByRole('list', { name: t('page.G1.top5') });
    expect(screen.queryByTestId('benchmark-absence')).toBeNull();
  });
});

describe('D10-1 G2·G3·G4 재판정 필요 배지', () => {
  it('G2 표: rejudge_needed 행에만 배지(가상 스크롤 행 그대로)', async () => {
    server.use(
      http.get(mswPath('/snapshots/:sid/complexes'), async ({ request }) => {
        const page = await example<ComplexRowPage>(request);
        const items = page.items.map((row, i) => ({ ...row, rejudge_needed: i === 0 }));
        return HttpResponse.json({ ...page, items });
      }),
    );
    renderRoute('/complexes');
    const table = await screen.findByRole('table', { name: t('page.G2.table') });
    await waitFor(() => expect(within(table).getAllByTestId('rejudge-needed')).toHaveLength(1));
    const row = within(table).getAllByTestId('rejudge-needed')[0]?.closest('tr');
    expect(row).toHaveAttribute('aria-rowindex', '2');
  });

  it('G3 헤더: 점수 행 rejudge_needed → 배지', async () => {
    server.use(
      http.get(mswPath('/complexes/:id'), async ({ request }) => {
        const detail = await example<ComplexDetail>(request);
        return HttpResponse.json({
          ...detail,
          score: detail.score ? { ...detail.score, rejudge_needed: true } : detail.score,
        });
      }),
    );
    renderRoute('/complexes/2');
    expect(await screen.findByTestId('rejudge-needed')).toHaveTextContent(
      t('page.common.rejudgeNeeded'),
    );
  });

  it('G4 비교 표: rejudge_needed 열의 순위 칸에 배지', async () => {
    server.use(
      http.get(mswPath('/snapshots/:sid/compare'), async ({ request }) => {
        const view = await example<CompareView>(request);
        return HttpResponse.json({
          ...view,
          rows: view.rows.map((row) => ({ ...row, rejudge_needed: row.complex_id === 7 })),
        });
      }),
    );
    renderRoute('/compare?ids=2,7,4&scenario=B');
    const grid = await screen.findByRole('table', { name: t('page.G4.grid') });
    await waitFor(() => expect(within(grid).getAllByTestId('rejudge-needed')).toHaveLength(1));
  });
});
