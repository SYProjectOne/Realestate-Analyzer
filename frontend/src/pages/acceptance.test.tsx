/**
 * WP6a 완료 기준(카드) — 화면 10개 핵심 요소, 숫자 셀 → 출처 패널, G2 1,000행 가상 스크롤.
 * MSW 핸들러 = 계약 예시(handlers.gen.ts) + 상태 보강(handlers.extra.ts).
 */
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import type { ComplexRow, ComplexRowPage } from '@/api/types';
import { t } from '@/i18n';
import { resetMockState } from '@/mocks/handlers.extra';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { renderRoute } from '@/test/render';
import './_shared/testing';

// jsdom에는 canvas가 없다 — ECharts 렌더러 자체는 Playwright(e2e/pages)가 본다
vi.mock('@/charts/EChartRuntime', () => ({ default: () => null }));

beforeEach(() => resetMockState());

describe('화면 10개 핵심 요소 (MSW)', () => {
  it('G0 /regions/new: 지역 검색창·분석 시작 버튼', async () => {
    renderRoute('/regions/new');
    expect(await screen.findByRole('searchbox', { name: t('page.G0.search') })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: t('page.G0.start') })).toBeDisabled();
  });

  it('G0-2 /regions/1/living-areas: 생활권 카드(이름 입력)와 저장 버튼', async () => {
    renderRoute('/regions/1/living-areas');
    const names = await screen.findAllByRole('textbox', { name: t('page.G0_2.areaName') });
    expect(names.length).toBeGreaterThanOrEqual(2);
    expect(screen.getByRole('button', { name: t('page.G0_2.save') })).toBeInTheDocument();
  });

  it('G1 /: KPI 타일 5개 · TOP 5 카드 · 최근 변경', async () => {
    renderRoute('/');
    // R9-UI P2: 시스템 지표 5칸 → 지금 접수 가능 카드 + 지역 현황 4칸(3단)
    // R11: 첫 줄 h1(접수 가능 N곳) + 지금 접수 가능한 단지 카드
    expect(
      await screen.findByRole('heading', { level: 1, name: new RegExp(`^${t('page.G1.title')}`) }),
    ).toBeInTheDocument();
    expect(
      await screen.findByRole('list', { name: t('page.G1.openNow.title') }),
    ).toBeInTheDocument();
    const kpis = await screen.findByRole('list', { name: t('page.G1.region') });
    // R11: 미분양 칸 안의 C05 범례(목록)는 빼고 칸 4개만
    expect(kpis.querySelectorAll(':scope > li')).toHaveLength(4);
    const top5 = screen.getByRole('list', { name: t('page.G1.top5') });
    expect(within(top5).getAllByRole('listitem').length).toBeGreaterThanOrEqual(5);
    expect(screen.getByRole('list', { name: t('page.G1.changes') })).toBeInTheDocument();
  });

  it('G2 /complexes: 단지 표(TanStack Table)·필터·CSV', async () => {
    renderRoute('/complexes');
    const table = await screen.findByRole('table', { name: t('page.G2.table') });
    await waitFor(() => expect(within(table).getAllByRole('row').length).toBeGreaterThan(2));
    expect(screen.getByRole('search', { name: t('page.G2.filters') })).toBeInTheDocument();
    // CSV 는 링크가 아니라 버튼(Bearer fetch → Blob 저장)
    expect(screen.getByRole('button', { name: t('page.G2.csv') })).toBeEnabled();
  });

  it('G3 /complexes/2: 헤더 접수 배지 + 탭 7개(D28-3 판정 기록은 근거 원문 안)', async () => {
    renderRoute('/complexes/2');
    const tablist = await screen.findByRole('tablist', { name: t('page.G3.tabs') });
    expect(within(tablist).getAllByRole('tab')).toHaveLength(7);
    expect(screen.getAllByTestId('intake-badge').length).toBeGreaterThan(0);
  });

  it('G4 /compare?ids=2,7,4: 단지 3열 비교 표', async () => {
    renderRoute('/compare?ids=2,7,4');
    const grid = await screen.findByRole('table', { name: t('page.G4.grid') });
    expect(within(grid).getAllByRole('columnheader')).toHaveLength(4);
  });

  it('G5 /scenario: 조건 폼 + 가중치 슬라이더 6개', async () => {
    renderRoute('/scenario');
    expect(await screen.findByRole('form', { name: t('page.G5.form') })).toBeInTheDocument();
    const weights = await screen.findByRole('group', { name: t('page.G5.weights') });
    await waitFor(() => expect(within(weights).getAllByRole('slider')).toHaveLength(6));
  });

  it('G6 /market: 벤치마크·입주 물량·미분양·호재 + 규제 카드', async () => {
    renderRoute('/market');
    expect(await screen.findByText(t('chart.C03.title'))).toBeInTheDocument();
    expect(screen.getByText(t('chart.C04.title'))).toBeInTheDocument();
    expect(screen.getByText(t('chart.C05.title'))).toBeInTheDocument();
    expect(screen.getByText(t('chart.C09.title'))).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: t('page.G6.regulation') })).toBeInTheDocument();
  });

  it('G7 /ops: 소스 상태 표 + 사람 확인 입력 폼', async () => {
    renderRoute('/ops');
    expect(await screen.findByRole('table', { name: t('page.G7.sources') })).toBeInTheDocument();
    expect(screen.getByRole('form', { name: t('page.G7.human') })).toBeInTheDocument();
  });

  it('G8 /reports: 생성 버튼 + 보고서 목록', async () => {
    renderRoute('/reports');
    expect(await screen.findByRole('button', { name: t('page.G8.generate') })).toBeInTheDocument();
    expect(await screen.findByRole('table', { name: t('page.G8.list') })).toBeInTheDocument();
  });
});

describe('숫자 셀 클릭 → 출처 패널', () => {
  it('G1 TOP 5 카드의 종합 점수를 누르면 출처 패널(dialog)이 열린다', async () => {
    renderRoute('/');
    const top5 = await screen.findByRole('list', { name: t('page.G1.top5') });
    const first = within(top5).getAllByRole('listitem')[0] as HTMLElement;
    const factButton = first.querySelector<HTMLButtonElement>('button[data-prov]');
    expect(factButton).not.toBeNull();
    await userEvent.click(factButton as HTMLButtonElement);
    const dialog = await screen.findByRole('dialog', { name: t('provenance.title') });
    // 출처 패널이 GET /provenance/{id}를 받아 라벨·원문 주소를 보인다
    expect(await within(dialog).findByText(t('provenance.url'))).toBeInTheDocument();
    // 카드 클릭으로 G3로 넘어가지 않았다
    expect(
      screen.getByRole('heading', { level: 1, name: new RegExp(`^${t('page.G1.title')}`) }),
    ).toBeInTheDocument();
  });
});

describe('G2 1,000행 가상 스크롤', () => {
  function bigPage(n: number): ComplexRowPage {
    const base: ComplexRow = {
      complex_id: 1,
      name: '단지',
      living_area: 'la_1',
      living_area_name: '생활권1',
      track: 'B',
      judge_scope: '판정 대상',
      intake: null,
      price_low: {
        v: 500_000_000,
        label: '확인됨',
        prov: 'fp_1',
        checked_at: '2026-10-07',
        human: false,
      },
      price_high: {
        v: 600_000_000,
        label: '확인됨',
        prov: 'fp_2',
        checked_at: '2026-10-07',
        human: false,
      },
      price_mid: {
        v: 550_000_000,
        label: '추정',
        prov: 'fp_3',
        checked_at: '2026-10-07',
        human: false,
      },
      resale_end: {
        v: '2027-01-01',
        label: '추정',
        prov: 'fp_4',
        checked_at: '2026-10-07',
        human: false,
      },
      move_in_ym: {
        v: '2028-03',
        label: '확인됨',
        prov: 'fp_5',
        checked_at: '2026-10-07',
        human: false,
      },
      gap_pct: { v: 1.5, label: '추정', prov: 'sc_1', checked_at: '2026-10-08', human: false },
      total: { v: 5, label: '추정', prov: 'st_1', checked_at: '2026-10-08', human: false },
      rank: 1,
      tie_group: null,
      unstable: false,
      p10: { v: 0.4, label: '추정', prov: 'jl_1', checked_at: '2026-10-07', human: false },
      inclusion_class: 'private_sale_apt',
      inclusion_decision: 'auto',
      inclusion_prob: { v: 1, label: '추정', prov: 'jl_2', checked_at: '2026-10-07', human: false },
      land_type: {
        v: '공공택지',
        label: '확인됨',
        prov: 'fp_6',
        checked_at: '2026-10-07',
        human: false,
      },
      price_cap: {
        v: '적용',
        label: '확인됨',
        prov: 'fp_7',
        checked_at: '2026-10-07',
        human: false,
      },
      regulated: {
        v: '비규제',
        label: '확인됨',
        prov: 'fp_8',
        checked_at: '2026-10-07',
        human: false,
      },
      residency_months: {
        v: 0,
        label: '확인됨',
        prov: 'fp_9',
        checked_at: '2026-10-07',
        human: false,
      },
      down_payment_pct: {
        v: 10,
        label: '확인됨',
        prov: 'fp_10',
        checked_at: '2026-10-07',
        human: false,
      },
      units_total: {
        v: 1000,
        label: '확인됨',
        prov: 'fp_11',
        checked_at: '2026-10-07',
        human: false,
      },
      last_change: null,
    };
    const items = Array.from({ length: n }, (_, i) => ({
      ...base,
      complex_id: i + 1,
      name: `가상단지 ${String(i + 1).padStart(4, '0')}`,
      rank: i + 1,
    }));
    return { items, total: n, snapshot_id: 12, asof_date: '2026-10-08', page: 1, size: n };
  }

  it('1,000행을 받아도 DOM에는 보이는 범위만 그리고, 스크롤하면 끝 행이 나온다', async () => {
    server.use(
      http.get(mswPath('/snapshots/:sid/complexes'), () => HttpResponse.json(bigPage(1000))),
    );
    renderRoute('/complexes');
    const table = await screen.findByRole('table', { name: t('page.G2.table') });
    await waitFor(() => expect(table).toHaveAttribute('aria-rowcount', '1001'));
    await screen.findByText('가상단지 0001');
    const rendered = within(table).getAllByRole('row').length;
    expect(rendered).toBeGreaterThan(1);
    expect(rendered).toBeLessThan(200);
    expect(screen.queryByText('가상단지 1000')).not.toBeInTheDocument();

    const scroller = screen.getByTestId('complex-table-scroll');
    scroller.scrollTop = 1_000_000;
    fireEvent.scroll(scroller);
    expect(await screen.findByText('가상단지 1000')).toBeInTheDocument();
    expect(within(table).getAllByRole('row').length).toBeLessThan(200);
  });
});
