import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { getResponse, http, HttpResponse, type RequestHandler } from 'msw';
import type { ComplexRow, Dashboard } from '@/api/types';
import { t } from '@/i18n';
import { generatedHandlers } from '@/mocks/handlers.gen';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { resetMockState } from '@/mocks/handlers.extra';
import { renderRoute } from '@/test/render';
import { matching, recordRequests } from '../_shared/testing';

vi.mock('@/charts/EChartRuntime', () => ({ default: () => null }));
beforeEach(() => resetMockState());

async function exampleDashboard(): Promise<Dashboard> {
  const res = await getResponse(
    generatedHandlers as RequestHandler[],
    new Request('http://localhost/api/snapshots/12/dashboard'),
  );
  return (await res?.json()) as Dashboard;
}

describe('R9-UI P2 G1 홈 첫 화면을 "지금 할 수 있는 것"부터(30-proposal §3)', () => {
  it('섹션 순서: 지금 접수 가능 → 다가오는 일정 → 종합 점수 상위 단지 → 지역 현황 → 최근 변경', async () => {
    const { container } = renderRoute('/');
    await screen.findByRole('list', { name: t('page.G1.top5') });
    const order = [...container.querySelectorAll('[data-section]')].map((el) =>
      el.getAttribute('data-section'),
    );
    expect(order).toEqual(['openNow', 'upcoming', 'top', 'region', 'changes']);
  });

  it('지금 접수 가능 N곳: 숫자는 FactCell(출처 유지), 링크 = G2 + 접수 가능 필터 + 전역 쿼리', async () => {
    const dash = await exampleDashboard();
    renderRoute('/?snapshot=12&scenario=B');
    const card = await screen.findByRole('region', { name: t('page.G1.openNow.title') });
    const prov = dash.kpis.intake_open_count.prov;
    expect(prov).toBeTruthy();
    const cell = card.querySelector(`[data-prov="${prov ?? ''}"]`) as HTMLElement;
    expect(cell).not.toBeNull();
    expect(within(cell).getByTestId('label-badge')).toBeInTheDocument();
    const link = within(card).getByRole('link', { name: t('page.G1.openNow.link') });
    const href = new URL(link.getAttribute('href') ?? '', 'http://x');
    expect(href.pathname).toBe('/complexes');
    expect(href.searchParams.get('intake_status')).toBe('가능');
    expect(href.searchParams.get('snapshot')).toBe('12');
    expect(href.searchParams.get('scenario')).toBe('B');
    expect(within(card).getByText(t('page.G1.openNow.hint'))).toBeInTheDocument();
  });

  it('최근 변경: 쉬운 문장, 바뀐 값(해시 등)은 "바뀐 값 보기"를 펼쳐야 보인다', async () => {
    const dash = await exampleDashboard();
    const change = dash.changes.find((c) => c.field !== 'first_load' && c.new_text);
    expect(change).toBeDefined();
    renderRoute('/');
    const feed = await screen.findByRole('list', { name: t('page.G1.changes') });
    const value = within(feed).getAllByTestId('change-value')[0] as HTMLElement;
    expect(value).not.toBeVisible();
    await userEvent.click(
      within(feed).getAllByText(t('page.G1.changeShowValue'))[0] as HTMLElement,
    );
    expect(value).toBeVisible();
    expect(value).toHaveTextContent(change?.new_text ?? '');
  });

  it('상위 단지가 5곳보다 적으면 이유 문장(개수는 메타)', async () => {
    const dash = await exampleDashboard();
    server.use(
      http.get(mswPath('/snapshots/:sid/dashboard'), () =>
        HttpResponse.json({ ...dash, top5: dash.top5.slice(0, 3) }),
      ),
    );
    renderRoute('/');
    const note = await screen.findByTestId('top5-fewer');
    expect(note).toHaveTextContent(t('page.G1.top5Fewer', { n: '3' }));
    expect(note.querySelector('[data-meta="count"]') ?? note).toBeTruthy();
    expect(screen.getByText(t('page.G1.top5Note'))).toBeInTheDocument();
  });
});

describe('G1 홈 대시보드', () => {
  it('지역 현황: 판정 대상·미분양·입주가 가장 많은 해·마지막 수집 — 값과 라벨 그대로(3단)', async () => {
    renderRoute('/');
    const region = await screen.findByRole('list', { name: t('page.G1.region') });
    for (const key of ['judged', 'unsold', 'movePeak', 'freshness'] as const) {
      const item = region.querySelector(`[data-kpi="${key}"]`) as HTMLElement;
      expect(item).not.toBeNull();
      expect(within(item).getByText(t(`page.G1.kpi.${key}`))).toBeInTheDocument();
      for (const cell of item.querySelectorAll('[data-prov]')) {
        expect(
          cell.querySelector('[data-testid="label-badge"], [data-testid="empty-state"]'),
        ).not.toBeNull();
      }
    }
  });

  it('TOP 5 카드: 종합·+10% 확률·접수 배지, 카드 클릭 → G3', async () => {
    const { router } = renderRoute('/');
    const top5 = await screen.findByRole('list', { name: t('page.G1.top5') });
    const cards = within(top5).getAllByRole('listitem');
    const first = cards[0] as HTMLElement;
    expect(within(first).getByText(t('page.G1.total'))).toBeInTheDocument();
    expect(within(first).getByText(t('page.G1.p10'))).toBeInTheDocument();
    expect(within(first).getByTestId('intake-badge')).toBeInTheDocument();
    await userEvent.click(within(first).getByText(t('page.G1.p10')));
    await waitFor(() =>
      expect(router.state.location.pathname).toBe(`/complexes/${first.dataset.complexId}`),
    );
  });

  it('변경 피드 항목 → G3 해당 탭(URL 해시)', async () => {
    renderRoute('/');
    const feed = await screen.findByRole('list', { name: t('page.G1.changes') });
    const links = within(feed).getAllByRole('link');
    expect(links[0]).toHaveAttribute('href', expect.stringMatching(/^\/complexes\/7.*#payment$/));
  });

  it('상황 토글 → ?scenario= 로 dashboard 재조회', async () => {
    const rec = recordRequests();
    renderRoute('/');
    await screen.findByRole('list', { name: t('page.G1.top5') });
    await userEvent.click(await screen.findByRole('radio', { name: /^B / }));
    await waitFor(() => {
      const calls = matching(rec.requests, 'GET', '/dashboard');
      expect(calls.some((c) => c.url.searchParams.get('scenario') === 'B')).toBe(true);
    });
    rec.stop();
  });
});

describe('R9-UI P2 G1 다가오는 일정 · TOP 카드 사실 줄(30-proposal §3, 갭 #15·#16)', () => {
  it('기준일부터 4주 안의 일정(최대 5건)만, 날짜순, D± · 종류 글자 · 접수일 미수집 안내', async () => {
    renderRoute('/');
    const box = await screen.findByRole('region', { name: t('page.G1.upcoming.title') });
    const items = await within(box).findAllByRole('listitem');
    expect(items.length).toBeGreaterThan(0);
    expect(items.length).toBeLessThanOrEqual(5);
    const dates = items.map((li) => li.getAttribute('data-due') ?? '');
    expect([...dates].sort()).toEqual(dates);
    for (const d of dates) {
      expect(d >= '2026-10-08' && d <= '2026-11-05').toBe(true);
    }
    for (const li of items) {
      expect(li.textContent).toMatch(/\(D[+-]\d+\)|D-day/);
      expect(within(li).getByTestId('schedule-kind').textContent?.length ?? 0).toBeGreaterThan(0);
    }
    expect(within(box).getByText(t('page.G1.upcoming.noApply'))).toBeInTheDocument();
    expect(within(box).getByRole('link', { name: t('page.G1.upcoming.all') })).toBeInTheDocument();
  });

  it('공유 토큰(403)이면 사유 문구', async () => {
    server.use(
      http.get(mswPath('/ops/checklist'), () =>
        HttpResponse.json({ code: 'forbidden', message: 'share token' }, { status: 403 }),
      ),
    );
    renderRoute('/');
    const box = await screen.findByRole('region', { name: t('page.G1.upcoming.title') });
    expect(await within(box).findByText(t('page.G1.upcoming.noAccess'))).toBeInTheDocument();
  });

  it('4주 안 일정이 없으면 그렇게 말한다', async () => {
    server.use(http.get(mswPath('/ops/checklist'), () => HttpResponse.json([])));
    renderRoute('/');
    const box = await screen.findByRole('region', { name: t('page.G1.upcoming.title') });
    expect(await within(box).findByText(t('page.G1.upcoming.none'))).toBeInTheDocument();
  });

  it('TOP 카드: 구매가·전매 종료·가격 갭 = 같은 리비전 목록 행의 Fact(prov 일치), 점수·+10%는 아래 칸', async () => {
    const rows = await exampleRows();
    renderRoute('/');
    const top5 = await screen.findByRole('list', { name: t('page.G1.top5') });
    const card = within(top5).getAllByRole('listitem')[0] as HTMLElement;
    const id = Number(card.dataset.complexId);
    const row = rows.find((r) => r.complex_id === id);
    expect(row).toBeDefined();
    const facts = card.querySelector('[data-card="facts"]') as HTMLElement;
    await waitFor(() =>
      expect(facts.querySelector(`[data-prov="${row?.price_low.prov}"]`)).not.toBeNull(),
    );
    for (const fact of [row?.price_high, row?.resale_end, row?.gap_pct]) {
      if (fact?.prov) expect(facts.querySelector(`[data-prov="${fact.prov}"]`)).not.toBeNull();
    }
    const score = card.querySelector('[data-card="score"]') as HTMLElement;
    expect(facts.compareDocumentPosition(score) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(within(score).getByText(t('page.G1.p10Note'))).toBeInTheDocument();
    // rerank 변화는 카드에서 빠지고 G3 점수 줄·G4·G5 에 그대로(30-proposal §3-5)
    expect(within(card).queryByTestId('top5-delta-rerank')).toBeNull();
  });

  it('목록 행이 없으면 사실 줄은 확인 불가(사유)', async () => {
    server.use(
      http.get(mswPath('/snapshots/:sid/complexes'), () =>
        HttpResponse.json({
          items: [],
          total: 0,
          snapshot_id: 12,
          asof_date: '2026-10-08',
          page: 1,
          size: 100,
        }),
      ),
    );
    renderRoute('/');
    const top5 = await screen.findByRole('list', { name: t('page.G1.top5') });
    const card = within(top5).getAllByRole('listitem')[0] as HTMLElement;
    const facts = card.querySelector('[data-card="facts"]') as HTMLElement;
    await waitFor(() =>
      expect(
        within(facts).getAllByText(t('empty.unknownWithReason', { reason: t('page.G1.noListRow') }))
          .length,
      ).toBeGreaterThan(0),
    );
  });
});

async function exampleRows(): Promise<ComplexRow[]> {
  const res = await getResponse(
    generatedHandlers as RequestHandler[],
    new Request('http://localhost/api/snapshots/12/complexes'),
  );
  return ((await res?.json()) as { items: ComplexRow[] }).items;
}
