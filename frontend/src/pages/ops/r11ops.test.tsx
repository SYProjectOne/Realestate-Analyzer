/**
 * R11-MARKETOPS(D30, 목업 Ops.dc.html) — G7 '오늘 확인할 것' 타일 · 묶음 메뉴 · 묶음 카드(질문형 제목 + "이게 뭐예요?") ·
 * 모순 주장 상태별 줄 수(상태 필터 없는 목록) · 작업 쉬운 이름(D30-8) · 닫힌·꺼진 줄 흐리게 · 앵커 유지.
 * 타일 값은 서버 수 또는 줄 개수만(D25-3) — 화면이 판단 이름을 붙이지 않는다.
 */
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { getResponse, http, HttpResponse, type RequestHandler } from 'msw';
import { ROLE_STORAGE_KEY, TOKEN_STORAGE_KEY } from '@/api/auth';
import type { ChecklistItem, ClaimView, IntakeQueue, SourceStatus } from '@/api/types';
import { jobNameText } from '@/components';
import { t } from '@/i18n';
import { metaText } from '@/lib/meta';
import { resetMockState } from '@/mocks/handlers.extra';
import { generatedHandlers } from '@/mocks/handlers.gen';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { renderRoute } from '@/test/render';
import { HUMAN_CHECK_ANCHOR } from './HumanCheckForm';
import { claimStatusCounts, contradictedClaims } from './ClaimsPanel';
import { INTAKE_QUEUE_ANCHOR } from './IntakeQueuePanel';
import { OPS_SECTIONS } from './sections';
import { addDays, dueCounts, intakeCategoryCounts } from './TodayTiles';

vi.mock('@/charts/EChartRuntime', () => ({ default: () => null }));
beforeEach(() => resetMockState());

/** 생성 핸들러 응답을 받아 고친다 */
function patch<T>(path: string, fn: (body: T) => T) {
  server.use(
    http.get(mswPath(path), async ({ request }) => {
      const res = await getResponse(generatedHandlers as RequestHandler[], request.clone());
      return HttpResponse.json(fn((await res?.json()) as T) as never);
    }),
  );
}

const claim = (id: number, verify_status: ClaimView['verify_status']): ClaimView => ({
  id,
  snapshot_id: 12,
  section: 'complex:11',
  complex_id: 11,
  complex_name: '고촌센트럴자이',
  text: `문장 ${id}`,
  evidence_text: null,
  verify_status,
  judgment_seq: null,
  prov: null,
  parent_claim_id: null,
  ordinal: 0,
  child_count: 0,
  remaining: verify_status === 'contradicted',
  pending_job_id: null,
  entity: null,
  entity_id: null,
  field: null,
  field_name: null,
  demotion: null,
});

describe('R11 G7 순수 함수(줄 세기만)', () => {
  it('addDays · dueCounts: 열린 항목만, 기준일~+14일 = 다가오는 기한, 기준일 전 = 지난 기한', () => {
    expect(addDays('2026-10-08', 14)).toBe('2026-10-22');
    const items = [
      { status: 'open', due_date: '2026-10-08' },
      { status: 'open', due_date: '2026-10-22' },
      { status: 'open', due_date: '2026-10-23' },
      { status: 'open', due_date: '2026-10-01' },
      { status: 'done', due_date: '2026-10-10' },
      { status: 'open', due_date: null },
    ] as ChecklistItem[];
    expect(dueCounts(items, '2026-10-08')).toEqual({
      soon: 2,
      overdue: 1,
      from: '2026-10-08',
      to: '2026-10-22',
    });
  });

  it('intakeCategoryCounts: 분류별 항목 줄 수(서버 순서)', () => {
    const q = {
      groups: [
        { category: 'collect_failed', reason: 'a', count: 2, items: [{}, {}] },
        { category: 'identity', reason: 'b', count: 1, items: [{}] },
        { category: 'collect_failed', reason: 'c', count: 1, items: [{}] },
      ],
    } as unknown as IntakeQueue;
    expect(intakeCategoryCounts(q)).toEqual([
      { category: 'collect_failed', n: 3 },
      { category: 'identity', n: 1 },
    ]);
  });

  it('claimStatusCounts · contradictedClaims: 서버 verify_status 를 세기만', () => {
    const rows = [
      claim(1, 'verified'),
      claim(2, 'contradicted'),
      claim(3, 'verified'),
      claim(4, 'review'),
      claim(5, null),
    ];
    expect(contradictedClaims(rows).map((c) => c.id)).toEqual([2]);
    expect(claimStatusCounts(rows)).toEqual([
      { key: 'verified', n: 2 },
      { key: 'contradicted', n: 1 },
      { key: 'unsupported', n: 0 },
      { key: 'review', n: 1 },
      { key: 'none', n: 1 },
    ]);
  });

  it('묶음 9개 · 앵커 #intake-queue · #human-check 는 기존 값', () => {
    expect(OPS_SECTIONS).toHaveLength(9);
    expect(INTAKE_QUEUE_ANCHOR).toBe('intake-queue');
    expect(HUMAN_CHECK_ANCHOR).toBe('human-check');
    expect(OPS_SECTIONS.map((s) => s.id)).toContain('intake-queue');
    expect(OPS_SECTIONS.map((s) => s.id)).toContain('human-check');
  });
});

describe('R11 G7 화면', () => {
  it('머리: 질문형 h1 + 운영자용 머리말(지역·기준일) + 안내', async () => {
    renderRoute('/ops');
    expect(
      await screen.findByRole('heading', { level: 1, name: t('page.G7.title') }),
    ).toBeInTheDocument();
    expect(await screen.findByTestId('ops-kicker')).toHaveTextContent(/운영자용 화면/);
    expect(screen.getByText(t('page.G7.intro'))).toBeInTheDocument();
  });

  it('오늘 확인할 것 타일 4장: 대기열 total · 분류별 줄 수 · 실패 자료 줄 수 · 모순 줄 수 · 기한 줄 수', async () => {
    patch<ClaimView[]>('/snapshots/:sid/claims', () => [
      claim(1, 'verified'),
      claim(2, 'contradicted'),
      claim(3, 'contradicted'),
      claim(4, 'review'),
    ]);
    renderRoute('/ops');
    const tiles = await screen.findByTestId('today-tiles');
    // 첫 로딩 타일(불러오는 중) 뒤에 실제 타일이 새로 그려진다 — 늘 다시 찾는다
    const tile = (k: string) => within(tiles).getByTestId(`tile-${k}`);
    // 계약 예시 대기열 total 7, 수집 실패 3 · 공식 홈페이지 확인 1 · …
    await waitFor(() =>
      expect(tile('intake')).toHaveTextContent(metaText('page.G7.today.countCases', { n: 7 })),
    );
    const intake = tile('intake');
    expect(within(intake).getByTestId('tile-intake-parts')).toHaveTextContent(
      metaText('page.G7.today.part', {
        name: t('page.G7.iq.categoryShort.collect_failed'),
        n: 3,
      }),
    );
    expect(intake).toHaveAttribute('href', expect.stringContaining('#intake-queue'));
    await waitFor(() =>
      expect(tile('sources')).toHaveTextContent(metaText('page.G7.today.countKinds', { n: 1 })),
    );
    expect(tile('sources')).toHaveTextContent(t('page.G7.sourceKind.official_site'));
    await waitFor(() =>
      expect(tile('claims')).toHaveTextContent(metaText('page.G7.today.countCases', { n: 2 })),
    );
    expect(tile('claims')).toHaveTextContent(t('page.G7.today.claimsSub'));
    await waitFor(() => expect(tile('checklist')).toHaveTextContent(/\d건/));
    expect(screen.getByText(t('page.G7.today.rule'))).toBeInTheDocument();
    // 판단 이름(급한 것·나중에)을 붙이지 않는다
    expect(tiles).not.toHaveTextContent(/급한|나중에/);
  });

  it('묶음 메뉴 9칸(쓰기 토큰) — 묶음마다 질문형 h2 · "이게 뭐예요?" · 머리말 번호', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-w');
    window.localStorage.setItem(ROLE_STORAGE_KEY, 'write');
    renderRoute('/ops');
    const nav = await screen.findByRole('navigation', { name: t('page.G7.menu.title') });
    const links = within(nav).getAllByRole('link');
    expect(links).toHaveLength(9);
    expect(within(nav).getByTestId('ops-menu-intake')).toHaveAttribute(
      'href',
      expect.stringContaining('#intake-queue'),
    );
    expect(within(nav).getByTestId('ops-menu-human')).toHaveAttribute(
      'href',
      expect.stringContaining('#human-check'),
    );
    for (const s of OPS_SECTIONS) {
      const section = await screen.findByTestId(`ops-section-${s.key}`);
      expect(section).toHaveAttribute('id', s.id);
      expect(
        within(section).getByRole('heading', { level: 2, name: t(`page.G7.q.${s.key}`) }),
      ).toBeInTheDocument();
      expect(within(section).getByText(t('page.G7.what'))).toBeInTheDocument();
      expect(section).toHaveTextContent(`${s.no} ${t(`page.G7.menu.${s.key}`)}`);
    }
  });

  it('읽기 전용 토큰이면 공유 링크 메뉴·묶음이 없다(8칸)', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-r');
    window.localStorage.setItem(ROLE_STORAGE_KEY, 'read');
    renderRoute('/ops');
    const nav = await screen.findByRole('navigation', { name: t('page.G7.menu.title') });
    expect(within(nav).getAllByRole('link')).toHaveLength(8);
    expect(within(nav).queryByTestId('ops-menu-share')).toBeNull();
    expect(screen.queryByTestId('ops-section-share')).toBeNull();
  });

  it('모순 주장: 상태 필터 없이 받은 목록의 상태별 줄 수 + 모순 줄만 목록에', async () => {
    patch<ClaimView[]>('/snapshots/:sid/claims', () => [
      claim(1, 'verified'),
      claim(2, 'contradicted'),
      claim(3, 'unsupported'),
    ]);
    renderRoute('/ops');
    const section = await screen.findByRole('region', { name: t('page.G7.claims.title') });
    const summary = await within(section).findByTestId('claims-summary');
    expect(summary).toHaveTextContent(metaText('page.G7.claims.summary', { n: 1 }));
    const breakdown = within(summary).getByTestId('claims-breakdown');
    expect(
      within(breakdown).getByText(t('page.G7.claims.status.verified'), { exact: false }),
    ).toBeInTheDocument();
    expect(within(section).getByTestId('claim-2')).toBeInTheDocument();
    expect(within(section).queryByTestId('claim-1')).toBeNull();
    expect(within(section).queryByTestId('claim-3')).toBeNull();
  });

  it('모순 주장이 없으면 "남은 모순 주장이 없어요" + 상태별 줄 수는 그대로', async () => {
    patch<ClaimView[]>('/snapshots/:sid/claims', () => [claim(1, 'verified')]);
    renderRoute('/ops');
    const section = await screen.findByRole('region', { name: t('page.G7.claims.title') });
    const summary = await within(section).findByTestId('claims-summary');
    expect(summary).toHaveTextContent(t('page.G7.claims.none'));
    expect(within(summary).getByTestId('claims-breakdown')).toBeInTheDocument();
  });

  it('작업 대기열: 쉬운 작업 이름(jobNameText, D30-8) + 원래 이름', async () => {
    renderRoute('/ops');
    const table = await screen.findByRole('table', { name: t('page.G7.queue') });
    const rows = within(table).getAllByRole('row').slice(1);
    expect(rows.length).toBeGreaterThan(0);
    const raw = within(rows[0] as HTMLElement).getByTestId('job-raw').textContent ?? '';
    const name = raw.split(' · ')[1] ?? '';
    expect(rows[0]).toHaveTextContent(jobNameText(name));
  });

  it('닫힌 체크리스트 줄·꺼진 자료 줄은 흐리게(data 표시 + 회색)', async () => {
    // 계약 예시: news 자료가 꺼져 있다
    patch<SourceStatus[]>('/ops/sources', (rows) => rows);
    renderRoute('/ops');
    const checklist = await screen.findByRole('table', { name: t('page.G7.checklist') });
    const closed = within(checklist)
      .getAllByRole('row')
      .filter((r) => r.getAttribute('data-closed') === 'true');
    expect(closed.length).toBeGreaterThan(0);
    for (const r of closed) expect(r.className).toMatch(/text-grayed/);
    expect(screen.getByText(t('page.G7.closedNote'))).toBeInTheDocument();
    const sources = await screen.findByRole('table', { name: t('page.G7.sources') });
    const off = within(sources)
      .getAllByRole('row')
      .filter((r) => r.getAttribute('data-enabled') === 'false');
    expect(off.length).toBeGreaterThan(0);
    for (const r of off) expect(r.className).toMatch(/text-grayed/);
  });

  it('달력은 체크리스트 묶음 안(달력 이름 목록 유지)', async () => {
    renderRoute('/ops');
    const section = await screen.findByTestId('ops-section-checklist');
    expect(
      await within(section).findByRole('list', { name: t('page.G7.calendar') }),
    ).toBeInTheDocument();
  });
});

describe('R11 G7 "구현할 때 지금 동작 그대로 유지"(OP-13)', () => {
  it('지역 로딩 동안에도 수집 상태 자리를 미리 잡는다(min-h-96, CLS)', async () => {
    renderRoute('/ops');
    const section = await screen.findByTestId('ops-section-sources');
    expect(section.className).toMatch(/min-h-96/);
  });

  it('다른 화면에서 #human-check 로 들어오면 사람 확인 폼으로 한 번 스크롤', async () => {
    const spy = vi.fn();
    const original = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = spy;
    try {
      renderRoute('/ops?hc_complex=1&hc_field=discount#human-check');
      await screen.findByRole('form', { name: t('page.G7.human') });
      await waitFor(() => expect(spy).toHaveBeenCalled());
      expect(document.getElementById('human-check')).not.toBeNull();
    } finally {
      Element.prototype.scrollIntoView = original;
    }
  });

  it('메뉴를 누르면 주소 해시가 그 묶음 id 가 되고 쿼리는 그대로', async () => {
    const { router } = renderRoute('/ops?region=1');
    const nav = await screen.findByRole('navigation', { name: t('page.G7.menu.title') });
    await userEvent.click(within(nav).getByTestId('ops-menu-claims'));
    await waitFor(() => expect(router.state.location.hash).toBe('#claims'));
    expect(router.state.location.search).toBe('?region=1');
    expect(within(nav).getByTestId('ops-menu-claims')).toHaveAttribute('aria-current', 'location');
  });
});

describe('R11 G7 앵커 #claims(G8 "모순 주장이 남아 막힘" 링크)', () => {
  it('모순 주장 묶음 id = claims, /ops#claims 로 들어오면 그 묶음으로 스크롤', async () => {
    const calls: string[] = [];
    const original = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = function (this: Element) {
      calls.push(this.id);
    };
    try {
      renderRoute('/ops#claims');
      const section = await screen.findByRole('region', { name: t('page.G7.claims.title') });
      expect(section).toHaveAttribute('id', 'claims');
      await waitFor(() => expect(calls).toContain('claims'));
      // 다른 앵커는 그대로
      expect(document.getElementById('intake-queue')).not.toBeNull();
      expect(document.getElementById('human-check')).not.toBeNull();
    } finally {
      Element.prototype.scrollIntoView = original;
    }
  });

  it('/ops#intake-queue 도 같은 방식으로 그 묶음으로 스크롤', async () => {
    const calls: string[] = [];
    const original = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = function (this: Element) {
      calls.push(this.id);
    };
    try {
      renderRoute('/ops#intake-queue');
      await screen.findByRole('region', { name: t('page.G7.iq.title') });
      await waitFor(() => expect(calls).toContain('intake-queue'));
    } finally {
      Element.prototype.scrollIntoView = original;
    }
  });
});
