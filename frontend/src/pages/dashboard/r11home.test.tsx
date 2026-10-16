/**
 * R11-HOME(D30, Main 보드) — G1 새 모양: 첫 줄 · 접수 가능 카드 · 곧 청약 접수 띠 · 다가오는 일정 D± 상자 · 지역 시장(C05 전체) ·
 * 점수 줄 C06 막대 · 알림 띠(SH-7·SH-8) · 휴대폰 접기 · 바닥 글. coverage-Main.md `테스트` 열이 가리키는 테스트.
 */
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { getResponse, http, HttpResponse, type RequestHandler } from 'msw';
import type { ChecklistItem, ComplexRowPage, Dashboard } from '@/api/types';
import { chartModules, DEFAULT_PALETTE } from '@/charts';
import { t } from '@/i18n';
import { MOBILE_QUERY } from '@/lib/useMediaQuery';
import { generatedHandlers } from '@/mocks/handlers.gen';
import { resetMockState } from '@/mocks/handlers.extra';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { renderRoute } from '@/test/render';
import { matching, recordRequests } from '../_shared/testing';
import { APPLY_SOON_DAYS, OPEN_CARDS, pickApplySoon } from './Hero';
import { rowBarOption } from './Ranking';
import { UPCOMING_DAYS, UPCOMING_MAX, upcomingItems } from './Schedule';

vi.mock('@/charts/EChartRuntime', () => ({ default: () => null }));
beforeEach(() => resetMockState());

async function example<T>(path: string): Promise<T> {
  const res = await getResponse(
    generatedHandlers as RequestHandler[],
    new Request(`http://localhost/api${path}`),
  );
  return (await res?.json()) as T;
}

function patchDashboard(fn: (d: Dashboard) => Dashboard) {
  server.use(
    http.get(mswPath('/snapshots/:sid/dashboard'), async () =>
      HttpResponse.json(fn(await example<Dashboard>('/snapshots/12/dashboard'))),
    ),
  );
}

function item(over: Partial<ChecklistItem>): ChecklistItem {
  return {
    id: 1,
    complex_id: 7,
    complex_name: '단지A',
    kind: '청약 접수',
    title: '1순위 청약 접수(해당지역)',
    due_date: '2026-10-20',
    status: 'open',
    note: null,
    ...over,
  };
}

describe('G1 첫 줄(hero, HM-1)', () => {
  it('h1 = "지금 청약을 넣을 수 있는 단지는 N곳이에요", N 은 KPI FactCell(라벨·출처), 앞에 화면 이름', async () => {
    const dash = await example<Dashboard>('/snapshots/12/dashboard');
    renderRoute('/');
    const count = await screen.findByTestId('hero-count');
    const h1 = count.closest('h1') as HTMLElement;
    expect(h1).toHaveAccessibleName(
      new RegExp(`^${t('page.G1.title')} ${t('page.G1.hero.before').trim()}`),
    );
    expect(
      count.querySelector(`[data-prov="${dash.kpis.intake_open_count.prov ?? ''}"]`),
    ).not.toBeNull();
    expect(within(count).getByTestId('label-badge')).toBeInTheDocument();
    // 앞글: {지역} · 기준일 {날짜}
    expect(screen.getByTestId('hero-lead')).toHaveTextContent(dash.asof_date);
  });

  it('데이터 전에는 h1 = 화면 이름 "홈"', async () => {
    renderRoute('/');
    expect(
      await screen.findByRole('heading', { level: 1, name: t('page.G1.title') }),
    ).toBeInTheDocument();
  });
});

describe('지금 접수 가능한 단지 카드(새로 더한 것 N2)', () => {
  it('목록 API 를 filter[intake_status]=가능 · sort=intake · size 3 으로 부르고, 카드 값은 목록 행 Fact 그대로', async () => {
    const rec = recordRequests();
    renderRoute('/?scenario=B');
    const list = await screen.findByRole('list', { name: t('page.G1.openNow.title') });
    const call = matching(rec.requests, 'GET', /\/complexes$/)[0];
    expect(call?.url.searchParams.get('filter[intake_status]')).toBe('가능');
    expect(call?.url.searchParams.get('sort')).toBe('intake');
    expect(call?.url.searchParams.get('size')).toBe(String(OPEN_CARDS));
    expect(call?.url.searchParams.get('scenario')).toBe('B');
    rec.stop();
    const page = await example<ComplexRowPage>(
      '/snapshots/12/complexes?filter[intake_status]=가능&sort=intake&size=3',
    );
    const cards = within(list).getAllByRole('listitem');
    expect(cards.length).toBeLessThanOrEqual(OPEN_CARDS);
    const first = cards[0] as HTMLElement;
    const row = page.items.find((r) => String(r.complex_id) === first.dataset.complexId);
    expect(row).toBeDefined();
    for (const f of [row?.price_low, row?.price_high, row?.resale_end, row?.move_in_ym]) {
      if (f?.prov) expect(first.querySelector(`[data-prov="${f.prov}"]`)).not.toBeNull();
    }
    expect(within(first).getByRole('link', { name: row?.name ?? '' })).toHaveAttribute(
      'href',
      expect.stringMatching(new RegExp(`^/complexes/${row?.complex_id}`)),
    );
    expect(within(first).getByTestId('intake-badge')).toBeInTheDocument();
  });

  it('접수 가능 단지가 없으면 안내 한 줄', async () => {
    server.use(
      http.get(mswPath('/snapshots/:sid/complexes'), () =>
        HttpResponse.json({ page: 1, size: 3, total: 0, asof_date: '2026-10-08', items: [] }),
      ),
    );
    renderRoute('/');
    expect(await screen.findByTestId('open-now-none')).toHaveTextContent(t('page.G1.openNow.none'));
  });
});

describe('곧 청약 접수 띠(새로 더한 것 N3) — 날짜 고르기만', () => {
  const asof = '2026-10-08';
  it('4주 안 가장 이른 열린 청약 접수의 단지, 그 단지의 청약 접수·당첨자 발표를 날짜순', () => {
    const items = [
      item({ id: 1, complex_id: 9, due_date: '2026-11-20' }), // 28일 밖
      item({ id: 2, complex_id: 7, due_date: '2026-10-21', title: '2순위 청약 접수' }),
      item({ id: 3, complex_id: 7, due_date: '2026-10-20' }),
      item({
        id: 4,
        complex_id: 7,
        kind: '당첨자 발표',
        title: '당첨자 발표',
        due_date: '2026-10-27',
      }),
      item({ id: 5, complex_id: 7, kind: '중도금', title: '중도금 1회', due_date: '2026-10-25' }),
      item({ id: 6, complex_id: 7, status: 'done', due_date: '2026-10-19' }),
      item({ id: 7, complex_id: 8, due_date: '2026-10-22' }),
    ];
    const pick = pickApplySoon(items, asof);
    expect(pick?.complexId).toBe(7);
    expect(pick?.items.map((i) => i.id)).toEqual([3, 2, 4]);
    expect(APPLY_SOON_DAYS).toBe(28);
  });

  it('고를 단지가 없으면 null(띠 없음)', () => {
    expect(pickApplySoon([item({ due_date: '2026-12-31' })], asof)).toBeNull();
    expect(pickApplySoon([item({ kind: '계약' })], asof)).toBeNull();
  });

  it('띠: 단지 이름 + 일정 칸(D±) + "일정·필요한 돈 보기" → G3 #payment', async () => {
    renderRoute('/');
    const band = await screen.findByRole('region', { name: t('page.G1.applySoon.title') });
    expect(within(band).getAllByRole('listitem').length).toBeGreaterThan(0);
    for (const li of within(band).getAllByRole('listitem')) {
      expect(li.textContent).toMatch(/D[+-]\d+|D-day/);
    }
    expect(within(band).getByRole('link', { name: t('page.G1.applySoon.link') })).toHaveAttribute(
      'href',
      expect.stringMatching(/^\/complexes\/\d+.*#payment$/),
    );
  });
});

describe('다가오는 일정(4주 · 최대 5건, HM-3·HM-4)', () => {
  it('upcomingItems: 열린 항목 · 기준일부터 28일 · 날짜순 · 최대 5건', () => {
    const many = Array.from({ length: 8 }, (_, i) =>
      item({ id: i + 1, due_date: `2026-10-${String(10 + i).padStart(2, '0')}` }),
    );
    const out = upcomingItems(
      [...many, item({ id: 99, due_date: '2026-12-01' }), item({ id: 98, status: 'na' })],
      '2026-10-08',
    );
    expect(out).toHaveLength(UPCOMING_MAX);
    expect(out.map((i) => i.due_date)).toEqual([...out.map((i) => i.due_date)].sort());
    expect(UPCOMING_DAYS).toBe(28);
  });

  it('왼쪽 D± 상자 · 단지 없는 항목은 제목 글자 · title = 서버 원래 제목', async () => {
    server.use(
      http.get(mswPath('/ops/checklist'), () =>
        HttpResponse.json([
          item({ id: 1, due_date: '2026-10-08' }),
          item({
            id: 2,
            complex_id: null,
            complex_name: null,
            kind: '사실 재확인',
            title: '지역 재확인',
            due_date: '2026-10-09',
          }),
        ]),
      ),
    );
    renderRoute('/');
    const box = await screen.findByRole('region', { name: t('page.G1.upcoming.title') });
    const items = await within(box).findAllByRole('listitem');
    expect(within(items[0] as HTMLElement).getByTestId('schedule-dday')).toHaveTextContent('D-day');
    expect(items[1]).toHaveAttribute('title', '지역 재확인');
    expect(within(items[1] as HTMLElement).queryByRole('link')).toBeNull();
    expect(within(items[1] as HTMLElement).getByText('지역 재확인')).toBeInTheDocument();
  });
});

describe('{지역} 시장 한눈에(HM-10~13)', () => {
  it('칸 4개(미분양·입주가 가장 몰리는 해·점수를 매긴 단지·마지막으로 모은 때), 미분양 칸 안에 C05 전체 차트(범례·표로 보기)', async () => {
    renderRoute('/');
    const list = await screen.findByRole('list', { name: t('page.G1.region') });
    expect(list.querySelectorAll(':scope > li')).toHaveLength(4);
    const unsold = list.querySelector('[data-kpi="unsold"]') as HTMLElement;
    expect(within(unsold).getByText(t('chart.C05.title'))).toBeInTheDocument();
    expect(within(unsold).getByRole('button', { name: t('table.show') })).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: t('page.G1.regionMore') }).getAttribute('href'),
    ).toMatch(/^\/market/);
  });
});

describe('점수 순서 · C06 줄 막대(HM-5~9)', () => {
  it('rowBarOption: C06 option 그대로(계열·값), 이름 축 숨김, 점수 축 0~10 고정, 눈금은 마지막 줄만', async () => {
    const dash = await example<Dashboard>('/snapshots/12/dashboard');
    const row = dash.top5[0]!;
    const base = chartModules.C06.buildOption(
      { rows: [row], weights: dash.weights, orientation: 'horizontal' },
      { palette: DEFAULT_PALETTE },
    ) as { series: { data: unknown[] }[] };
    const opt = rowBarOption(row, { weights: dash.weights }, DEFAULT_PALETTE, false) as {
      series: { data: unknown[] }[];
      xAxis: { max: number; show: boolean };
      yAxis: { show: boolean };
    };
    expect(opt.series.map((s) => s.data)).toEqual(base.series.map((s) => s.data));
    expect(opt.xAxis.max).toBe(10);
    expect(opt.xAxis.show).toBe(false);
    expect(opt.yAxis.show).toBe(false);
    const last = rowBarOption(row, { weights: dash.weights }, DEFAULT_PALETTE, true) as {
      xAxis: { show: boolean };
    };
    expect(last.xAxis.show).toBe(true);
  });

  it('줄마다 "{이름} 점수 구성" 막대 · 범례(비중) · 바닥 "표로 보기" 펼치면 C06 표(순위·이름·종합·성분)', async () => {
    renderRoute('/');
    const list = await screen.findByRole('list', { name: t('page.G1.top5') });
    const rows = within(list).getAllByRole('listitem');
    for (const li of rows) {
      const name = li.querySelector('a')?.textContent ?? '';
      expect(
        within(li).getByRole('img', { name: t('page.G1.rankBar', { name }) }),
      ).toBeInTheDocument();
    }
    const section = list.closest('section') as HTMLElement;
    expect(within(section).getByTestId('chart-legend')).toBeInTheDocument();
    await userEvent.click(within(section).getByRole('button', { name: t('table.show') }));
    const table = within(section).getByRole('table');
    expect(
      within(table).getByText(t('table.caption', { title: t('chart.C06.title') })),
    ).toBeInTheDocument();
    expect(
      within(table).getByRole('columnheader', { name: t('chart.col.rank') }),
    ).toBeInTheDocument();
  });

  it("'+10% 이상 오를 가능성' 줄: 목표 시점(상황 p10_horizon) · 당첨 확률이 아니에요 · 보장 아님", async () => {
    renderRoute('/');
    const list = await screen.findByRole('list', { name: t('page.G1.top5') });
    const p10 = (within(list).getAllByRole('listitem')[0] as HTMLElement).querySelector(
      '[data-card="p10"]',
    ) as HTMLElement;
    expect(p10).toHaveTextContent(t('page.G1.p10Line'));
    await waitFor(() =>
      expect(within(p10).getByTestId('p10-target')).not.toHaveTextContent(t('empty.unknown')),
    );
    expect(p10).toHaveTextContent(t('page.G1.p10Note'));
  });
});

describe('알림 띠(Shell SH-7·SH-8)', () => {
  it('SH-7: 다시 판정이 필요해요 + 저장된 값 · 발행 순간 값과 다를 수 있음 + 다시 판정하기', async () => {
    patchDashboard((d) => ({ ...d, rejudge_needed: true }));
    renderRoute('/');
    const notice = await screen.findByTestId('rejudge-notice');
    expect(notice).toHaveTextContent(t('page.G1.rejudgeTitle'));
    expect(notice).toHaveTextContent(t('page.G1.rejudgeNotice'));
    expect(notice).toHaveTextContent(t('page.G1.rejudgeStored'));
    expect(within(notice).getByRole('button', { name: t('page.G1.rejudgeRun') })).toHaveAttribute(
      'data-write',
    );
  });

  it('SH-8: "근처 새 아파트 실적이 없어 종합 점수를 계산하지 않았어요"', async () => {
    patchDashboard((d) => ({ ...d, benchmark_absence: { code: 'no_sample', reason: '표본 0' } }));
    renderRoute('/');
    const notice = await screen.findByTestId('benchmark-absence');
    expect(notice).toHaveAttribute('data-banner-tone', 'note');
    expect(notice).toHaveTextContent('근처 새 아파트 실적이 없어 종합 점수를 계산하지 않았어요');
  });
});

describe('바닥 글 · 휴대폰 접기(HM-15·HM-16)', () => {
  it('바닥: 자격 판정 아님 + 출처 범례(라벨 뜻)', async () => {
    renderRoute('/');
    await screen.findByRole('list', { name: t('page.G1.top5') });
    expect(screen.getByText(t('page.G1.footNote'))).toBeInTheDocument();
    const foot = screen.getByText(t('page.G1.footNote')).closest('footer') as HTMLElement;
    expect(within(foot).getByText(t('label.legend'), { exact: false })).toBeInTheDocument();
  });

  it('휴대폰: 지역 시장 · 최근에 바뀐 것은 접힌 details', async () => {
    const original = window.matchMedia;
    window.matchMedia = ((query: string) => ({
      ...original(query),
      matches: query === MOBILE_QUERY,
    })) as typeof window.matchMedia;
    try {
      const { container } = renderRoute('/');
      await screen.findByRole('list', { name: t('page.G1.top5') });
      for (const section of ['region', 'changes']) {
        const el = container.querySelector(`[data-section="${section}"]`) as HTMLElement;
        expect(el.tagName).toBe('DETAILS');
        expect(el).not.toHaveAttribute('open');
      }
    } finally {
      window.matchMedia = original;
    }
  });
});
