import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { getResponse, http, HttpResponse, type RequestHandler } from 'msw';
import type { CompareView, LadderRow, Scenario } from '@/api/types';
import { t } from '@/i18n';
import { generatedHandlers } from '@/mocks/handlers.gen';
import { resetMockState } from '@/mocks/handlers.extra';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { renderRoute } from '@/test/render';
import { matching, recordRequests } from '../_shared/testing';
import { parseIds, verdictCounts } from './index';
import { p10TargetLine, targetText } from './parts';

vi.mock('@/charts/EChartRuntime', () => ({ default: () => null }));
beforeEach(() => resetMockState());

async function example<T>(path: string): Promise<T> {
  const res = await getResponse(
    generatedHandlers as RequestHandler[],
    new Request(new URL(`/api${path}`, 'http://localhost').toString()),
  );
  return (await res!.json()) as T;
}

/** 비교 응답 한 번 바꿔 돌려준다 */
function useCompareResponse(edit: (v: CompareView) => CompareView) {
  server.use(
    http.get(mswPath('/snapshots/:sid/compare'), async ({ request }) => {
      const res = await getResponse(generatedHandlers as RequestHandler[], request.clone());
      return HttpResponse.json(edit((await res!.json()) as CompareView));
    }),
  );
}

describe('G4 parseIds', () => {
  it('정수만, 중복 제거', () => {
    expect(parseIds('2,7,4')).toEqual([2, 7, 4]);
    expect(parseIds('2, 2, x, 0, -1, 3.5, 9')).toEqual([2, 9]);
    expect(parseIds(null)).toEqual([]);
  });
});

describe('G4 비교', () => {
  it.each([
    ['/compare?ids=2', 1],
    ['/compare?ids=1,2,3,4,5,6,7', 7],
    ['/compare', 0],
  ])('%s → ids 2~6 검사 안내(지금 n개) + 단지 찾기로 돌아가기, API 호출 없음', async (path, n) => {
    const rec = recordRequests();
    renderRoute(path);
    const box = await screen.findByTestId('compare-invalid');
    expect(box).toHaveTextContent(t('page.G4.invalidIds'));
    expect(box).toHaveTextContent(t('page.G4.invalidIdsNow', { n: String(n) }));
    const back = within(box).getByRole('link', { name: t('page.G4.backToList') });
    expect(back.getAttribute('href')).toMatch(/^\/complexes/);
    expect(matching(rec.requests, 'GET', '/compare')).toHaveLength(0);
    rec.stop();
  });

  it('머리: 위치 줄(단지 찾기 › 비교하기) · h1 · 요약 줄 · 단지 더 담기 · 출처 범례', async () => {
    renderRoute('/compare?ids=2,7,4&scenario=B');
    expect(
      await screen.findByRole('heading', { level: 1, name: t('page.G4.title') }),
    ).toBeInTheDocument();
    const crumb = screen.getByRole('navigation', { name: t('page.G4.crumb') });
    expect(within(crumb).getByRole('link', { name: t('nav.G2') })).toHaveAttribute(
      'href',
      '/complexes?scenario=B',
    );
    expect(within(crumb).getByText(t('nav.G4'))).toHaveAttribute('aria-current', 'page');
    expect(
      screen.getByRole('link', { name: new RegExp(t('page.G4.addMore').replace(/[()]/g, '.')) }),
    ).toHaveAttribute('href', '/complexes?scenario=B');
    await screen.findByRole('table', { name: t('page.G4.grid') });
    expect(
      screen.getByText(t('page.G4.summary', { n: '3', name: 'B 가점 낮음·소액 자기자본' })),
    ).toBeInTheDocument();
    expect(screen.getByText(t('label.legend'), { exact: false })).toBeInTheDocument();
  });

  it('비교 단지 카드 줄(N1): 단지마다 접수·생활권·이름 링크·입주·종합·순위, 순서 = 주소 ids', async () => {
    useCompareResponse((v) => ({ ...v, ids: [7, 2, 4] }));
    renderRoute('/compare?ids=7,2,4');
    const list = await screen.findByRole('list', { name: t('nav.G4') });
    const cards = within(list).getAllByTestId('compare-card');
    expect(cards.map((c) => within(c).getByRole('link').textContent)).toEqual([
      '김포 칸타빌 에디션',
      '엘리프 검단 포레듀',
      '오퍼스 한강 스위첸',
    ]);
    const first = cards[0] as HTMLElement;
    expect(within(first).getByRole('link').getAttribute('href')).toMatch(/^\/complexes\/7/);
    expect(within(first).getByTestId('intake-badge')).toBeInTheDocument();
    expect(first).toHaveTextContent(t('page.G4.card.moveIn'));
    expect(first).toHaveTextContent(t('page.G4.row.total'));
    expect(first).toHaveTextContent(t('page.G4.row.rank'));
    expect(within(first).getAllByTestId('label-badge').length).toBeGreaterThan(0);
  });

  it('표·차트 열 순서 = 주소 ids 순서(#18)', async () => {
    useCompareResponse((v) => ({ ...v, ids: [4, 2, 7] }));
    renderRoute('/compare?ids=4,2,7');
    const grid = await screen.findByRole('table', { name: t('page.G4.grid') });
    const heads = within(grid)
      .getAllByRole('columnheader')
      .slice(1)
      .map((th) => th.textContent);
    expect(heads).toEqual(['오퍼스 한강 스위첸', '엘리프 검단 포레듀', '김포 칸타빌 에디션']);
    const terms = screen.getByRole('table', { name: t('page.G4.termsFirst') });
    expect(
      within(terms)
        .getAllByRole('columnheader')
        .map((th) => th.textContent),
    ).toEqual([t('page.G4.termsCorner'), ...heads]);
  });

  it('비교 표(열 = 단지) · 조건 표 · 상황별 판정(C7) · 동률 배지', async () => {
    renderRoute('/compare?ids=2,7,4&scenario=B');
    const grid = await screen.findByRole('table', { name: t('page.G4.grid') });
    expect(within(grid).getAllByRole('columnheader')).toHaveLength(4);
    expect(within(grid).getByTestId('compare-decision')).toHaveTextContent(
      t('page.G4.row.decision', { name: 'B 가점 낮음·소액 자기자본' }),
    );
    expect(screen.getByRole('table', { name: t('page.G4.termsFirst') })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: t('chart.C07.title') })).toBeInTheDocument();
    // 상황 B 예시: confidence 0.48 → 동률
    expect(screen.getAllByTestId('tie-badge').length).toBeGreaterThan(0);
  });

  it("점수·판정기 행: 쉬운 이름 + (공식 이름), '오를 가능성'에 목표 시점·당첨 확률 아님·보장 아님·용어 ?", async () => {
    renderRoute('/compare?ids=2,7,4&scenario=B');
    const grid = await screen.findByRole('table', { name: t('page.G4.grid') });
    const rowOf = (name: string) => within(grid).getByRole('row', { name: new RegExp(`^${name}`) });
    expect(rowOf(t('page.G4.row.total'))).toHaveTextContent(t('page.G4.row.totalNote'));
    expect(rowOf(t('page.G4.row.rank'))).toHaveTextContent(t('page.G4.row.rankNote'));
    const p10 = within(grid).getByTestId('compare-p10');
    const head = within(p10).getByRole('rowheader');
    expect(head).toHaveTextContent(t('page.G4.row.p10'));
    // 상황 B 의 policy.p10_horizon = move_in_plus_1y (서버 시나리오 값)
    expect(head).toHaveTextContent(
      t('page.G4.row.p10Target', {
        target: t('chart.C01.horizon.move_in_plus_1y'),
        name: 'B 가점 낮음·소액 자기자본',
      }),
    );
    expect(head).toHaveTextContent(t('page.G4.row.p10Note'));
    expect(within(head).getByTestId('term')).toHaveAttribute('data-term', 'p10');
    expect(within(p10).getAllByRole('cell')).toHaveLength(3);
    for (const cell of within(p10).getAllByRole('cell')) {
      expect(within(cell).getByTestId('label-badge')).toBeInTheDocument();
    }
  });

  it('p10 목표 시점은 시나리오 policy 를 따른다(C = 기준일 + 5년), 모르면 일반 문구', () => {
    const c = {
      name: 'C 시세차익 우선',
      policy: { p10_horizon: 'asof_plus_5y' },
    } as unknown as Pick<Scenario, 'name' | 'policy'>;
    expect(p10TargetLine(c)).toBe(
      t('page.G4.row.p10Target', { target: t('chart.C01.horizon.asof_plus_5y'), name: c.name }),
    );
    expect(p10TargetLine(null)).toBe(t('page.G4.row.p10TargetAny'));
    expect(targetText(null)).toBeNull();
    expect(t('page.G4.row.p10')).toContain('오를 가능성');
    expect(t('page.G4.row.p10Note')).toContain('당첨 확률이 아니에요');
    expect(t('page.G4.row.p10Note')).toContain('보장 아님');
  });

  it('순위 칸: 순위 없으면 확인 불가 + 순위가 흔들려요·다시 판정 필요 배지(서버 값 그대로)', async () => {
    useCompareResponse((v) => ({
      ...v,
      rows: v.rows.map((r, i) =>
        i === 0 ? { ...r, rank: null, unstable: true, rejudge_needed: true } : r,
      ),
    }));
    renderRoute('/compare?ids=2,7,4');
    const grid = await screen.findByRole('table', { name: t('page.G4.grid') });
    const rank = within(grid).getByRole('row', { name: new RegExp(`^${t('page.G4.row.rank')}`) });
    const cell = within(rank).getAllByRole('cell')[0] as HTMLElement;
    expect(within(cell).getByTestId('empty-state')).toHaveTextContent(t('empty.unknown'));
    expect(within(cell).getByText(t('badge.unstable'))).toBeInTheDocument();
    expect(within(cell).getByTestId('rejudge-needed')).toHaveTextContent(
      t('page.common.rejudgeNeeded'),
    );
  });

  it('가상 후보 wait_new(complex_id null, 계약 .5) → 상황별 판정에 "가상 후보: <label>" + 고를 확률', async () => {
    renderRoute('/compare?ids=2,7,4&scenario=B');
    const panel = await screen.findByRole('region', { name: t('page.G4.decisionQ') });
    const list = await within(panel).findByRole('list', { name: t('page.G4.virtual') });
    const items = within(list).getAllByRole('listitem');
    expect(items).toHaveLength(1);
    const item = items[0] as HTMLElement;
    expect(item).toHaveAttribute('data-option', 'wait_new');
    expect(item).toHaveTextContent(
      t('page.G4.virtualCandidate', { label: '모집공고 대기 후 1순위 청약' }),
    );
    expect(item).toHaveTextContent(t('page.G4.row.prob'));
    expect(item).toHaveTextContent('0%');
    // 요건 표에서도 가상 후보임을 표시, 사전 계산이 없는 칸 = '사전 계산 없음'
    const req = within(panel).getByRole('table', { name: t('page.G4.requirements') });
    const row = within(req).getByRole('row', { name: /모집공고 대기 후 1순위 청약/ });
    expect(within(row).getByText(t('chart.C07.virtual'))).toBeInTheDocument();
    expect(within(row).getAllByText(t('page.G4.reqNone'))).toHaveLength(3);
  });

  it('wait_new 가 없는 상황(base) → 가상 후보 목록 없음 · 판정기 경고(서버 문장 그대로)', async () => {
    renderRoute('/compare?ids=2,7,4&scenario=base');
    const panel = await screen.findByRole('region', { name: t('page.G4.decisionQ') });
    expect(within(panel).queryByRole('list', { name: t('page.G4.virtual') })).toBeNull();
    const warn = within(panel).getByTestId('g4-warnings');
    expect(warn).toHaveTextContent(t('page.G4.warnings'));
    expect(within(warn).getAllByRole('listitem')).toHaveLength(1);
  });

  it('상황 고르기 라디오: 이름(서버) · 고르면 C7 이 그 상황으로, 키보드(Tab·Enter)로도', async () => {
    renderRoute('/compare?ids=2,7,4&scenario=B');
    const panel = await screen.findByRole('region', { name: t('page.G4.decisionQ') });
    const group = within(panel).getByRole('radiogroup', { name: t('page.G4.decisionPick') });
    const radios = within(group).getAllByRole('radio');
    expect(radios.map((r) => r.textContent)).toEqual(['B 가점 낮음·소액 자기자본', '기본']);
    expect(radios[0]).toHaveAttribute('aria-checked', 'true');
    (radios[1] as HTMLElement).focus();
    await userEvent.keyboard('{Enter}');
    expect(radios[1]).toHaveAttribute('aria-checked', 'true');
    // base 판정에는 경고가 있다
    expect(within(panel).getByTestId('g4-warnings')).toBeInTheDocument();
  });

  it('판정이 없으면 "이 상황의 판정이 없어요."', async () => {
    useCompareResponse((v) => ({ ...v, decisions: {} }));
    renderRoute('/compare?ids=2,7,4');
    const panel = await screen.findByRole('region', { name: t('page.G4.decisionQ') });
    expect(within(panel).getByText(t('page.G4.noDecision'))).toBeInTheDocument();
  });

  it('요건 표: 쉬운 열 이름 + (접근·규제·자금), 상태 배지·판정기 결론 문장(영문 값 아님)·근거와 달라요·근거 문장', async () => {
    renderRoute('/compare?ids=2,7,4&scenario=B');
    const panel = await screen.findByRole('region', { name: t('page.G4.decisionQ') });
    const req = within(panel).getByRole('table', { name: t('page.G4.requirements') });
    const heads = within(req).getAllByRole('columnheader');
    expect(heads.map((h) => h.textContent)).toEqual([
      t('page.G5.req.complex'),
      `${t('page.G5.req.access')} (${t('page.G5.reqTerm.access')})`,
      `${t('page.G5.req.regulation')} (${t('page.G5.reqTerm.regulation')})`,
      `${t('page.G5.req.funds')} (${t('page.G5.reqTerm.funds')})`,
    ]);
    const statuses = within(req)
      .getAllByTestId('req-status')
      .map((el) => el.getAttribute('data-status'));
    expect(new Set(statuses)).toEqual(new Set(['충족', '미충족', '확인 불가']));
    const judges = within(req).getAllByTestId('req-judge');
    expect(judges.length).toBeGreaterThan(0);
    const status = { supported: '충족', contradicted: '미충족', unknown: '확인 불가' } as const;
    for (const j of judges) {
      const judge = j.getAttribute('data-judge') as keyof typeof status;
      expect(j.textContent).toBe(t('page.G4.reqJudge', { status: status[judge] }));
    }
    expect(req.textContent ?? '').not.toMatch(/supported|contradicted|unknown/);
    expect(within(req).getAllByText(t('badge.mismatch')).length).toBeGreaterThan(0);
    expect(screen.getByText(new RegExp(t('page.G4.reqSource')))).toBeInTheDocument();
  });
});

describe('R9-UI P9 G4 사실 비교를 먼저(30-proposal §10)', () => {
  it('블록 순서: 조건 비교 → 점수·판정기 → 가격 갭 → 점수 분해 → 가격 전망 → 상황별 판정 → 민감도', async () => {
    const { container } = renderRoute('/compare?ids=2,7,4&scenario=B');
    await screen.findByRole('table', { name: t('page.G4.grid') });
    await waitFor(() => expect(container.querySelector('[data-block="C10"]')).not.toBeNull());
    const order = [...container.querySelectorAll('[data-block]')].map((el) =>
      el.getAttribute('data-block'),
    );
    expect(order).toEqual(['terms', 'grid', 'C02', 'C06', 'ladder', 'decision', 'C10']);
    // 구역 제목 = 질문형 h2, 차트 구역 앞 화면 낭독기용 h2 '차트'(#16)
    const h2 = screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent);
    expect(h2).toEqual([
      t('page.G4.termsQ'),
      t('page.G4.scoresQ'),
      t('page.common.charts'),
      t('page.G4.gapsQ'),
      t('page.G4.breakdownQ'),
      t('page.G4.ladderQ'),
      t('page.G4.decisionQ'),
      t('chart.C10.question'),
    ]);
    expect(screen.getByText(t('page.common.charts'))).toHaveClass('sr-only');
  });

  it('점수 순위와 판정기 고를 확률의 차이를 두 줄로 설명한다', async () => {
    renderRoute('/compare?ids=2,7,4');
    const scores = await screen.findByRole('region', { name: t('page.G4.scoresQ') });
    expect(within(scores).getByText(t('page.G4.scores'))).toBeInTheDocument();
    expect(within(scores).getByText(t('page.G4.rankNote'))).toBeInTheDocument();
    expect(within(scores).getByText(t('page.G4.decideNote'))).toBeInTheDocument();
  });

  it('조건 비교 표: 접수·지금 사는 값(Fact 그대로)·되팔 수 있는 날·계약금 — 쉬운 이름 + (공식 이름), 라벨·출처 유지', async () => {
    renderRoute('/compare?ids=2,7,4');
    const terms = await screen.findByRole('table', { name: t('page.G4.termsFirst') });
    const rowOf = (name: string) =>
      within(terms).getByRole('row', { name: new RegExp(`^${name}`) });
    expect(within(rowOf(t('page.G4.term.intake'))).getAllByTestId('intake-badge')).toHaveLength(3);
    const price = rowOf(t('page.G4.term.price'));
    expect(price).toHaveTextContent(`(${t('glossary.items.current_price.term')})`);
    const provs = [...price.querySelectorAll('[data-prov]')];
    expect(provs.length).toBeGreaterThan(0);
    for (const cell of provs) {
      expect(
        cell.querySelector('[data-testid="label-badge"], [data-testid="empty-state"]'),
      ).not.toBeNull();
    }
    const resale = rowOf(t('page.G4.term.resale_end'));
    expect(resale).toHaveTextContent(`(${t('glossary.items.resale_limit.term')})`);
    expect(within(resale).getByTestId('term')).toHaveAttribute('data-term', 'resale_end');
    expect(rowOf(t('page.G4.term.residency_months'))).toBeInTheDocument();
    expect(rowOf(t('page.G4.term.down_payment_pct'))).toBeInTheDocument();
    expect(rowOf(t('page.G4.term.down_payment_won'))).toBeInTheDocument();
    const equity = rowOf(t('page.G4.term.required_equity_won'));
    expect(within(equity).getByTestId('term')).toHaveAttribute('data-term', 'equity');
    expect(rowOf(t('page.G4.term.interim_terms_text'))).toHaveTextContent('중도금 60% 이자후불제');
    expect(
      screen.getByText(
        new RegExp(
          `^${t('page.G4.termsSourceNoAsof')} · ${t('chart.asofOnly', { asof: '2026-10-08' })}`,
        ),
      ),
    ).toBeInTheDocument();
  });

  it('조건 표 칸: 조건 행 없음 → 확인 불가 · 중도금 없음 → "공고에 따로 적힌 조건 없음" · 긴 글은 [전체 보기] · 자기자본 미입력 안내 → 내 조건', async () => {
    const long = '가'.repeat(80);
    useCompareResponse((v) => ({
      ...v,
      terms: [
        {
          ...v.terms[0]!,
          interim_terms_text: null,
          required_equity_won: {
            v: null,
            label: '확인 불가',
            reason: '내 조건 미입력',
            prov: null,
            checked_at: null,
          },
        },
        { ...v.terms[1]!, interim_terms_text: long },
      ],
    }));
    renderRoute('/compare?ids=2,7,4&scenario=B');
    const terms = await screen.findByRole('table', { name: t('page.G4.termsFirst') });
    const interim = within(terms).getByRole('row', {
      name: new RegExp(`^${t('page.G4.term.interim_terms_text')}`),
    });
    const cells = within(interim).getAllByRole('cell');
    expect(cells[0]).toHaveTextContent(t('page.G4.interimNone'));
    const more = within(cells[1] as HTMLElement).getByRole('button', {
      name: t('page.G4.interimMore'),
    });
    expect(more).toHaveAttribute('aria-expanded', 'false');
    await userEvent.click(more);
    expect(
      within(cells[1] as HTMLElement).getByRole('button', { name: t('page.G4.interimLess') }),
    ).toHaveAttribute('aria-expanded', 'true');
    // 셋째 단지(4)는 조건 행이 없다 → 확인 불가
    expect(within(cells[2] as HTMLElement).getByTestId('empty-state')).toBeInTheDocument();
    const note = screen.getByTestId('equity-note');
    expect(note).toHaveTextContent(t('page.G4.equityNote'));
    expect(within(note).getByRole('link', { name: t('nav.G5') })).toHaveAttribute(
      'href',
      '/scenario?scenario=B',
    );
  });
});

describe('R11 G4 차트 구역(목업 Compare)', () => {
  it('가격 갭: 단지마다 머리(서버 가격 갭 % + 부호 뜻 · 이 단지 중간 · 비교 단지 n곳) + C02(제목 = 단지 이름)', async () => {
    renderRoute('/compare?ids=2,7,4');
    const region = await screen.findByRole('region', { name: t('page.G4.gapsQ') });
    const cells = within(region).getAllByTestId('gap-cell');
    expect(cells).toHaveLength(3);
    const first = cells[0] as HTMLElement;
    const head = within(first).getByTestId('gap-head');
    expect(head).toHaveTextContent(t('page.G4.gapHead'));
    expect(head).toHaveTextContent('-5.2%');
    expect(within(head).getByTestId('label-badge')).toBeInTheDocument();
    expect(first).toHaveTextContent(t('page.G4.gapSign'));
    expect(first).toHaveTextContent(t('page.G4.gapMid'));
    expect(first).toHaveTextContent(t('page.G4.gapComps', { n: '3' }));
    expect(within(first).getByRole('heading', { name: '엘리프 검단 포레듀' })).toBeInTheDocument();
  });

  it('차트마다 기준일(asof) 바닥줄', async () => {
    renderRoute('/compare?ids=2,7,4');
    await screen.findByRole('table', { name: t('page.G4.grid') });
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: t('chart.C10.title') })).toBeInTheDocument(),
    );
    const figures = [...document.querySelectorAll('figure')];
    // C02 3장 + C06 + C01 + C07 + C10
    expect(figures).toHaveLength(7);
    for (const f of figures) expect(f).toHaveTextContent('2026-10-08');
  });

  it('점수 분해: 질문형 구역 + C06', async () => {
    renderRoute('/compare?ids=2,7,4');
    const region = await screen.findByRole('region', { name: t('page.G4.breakdownQ') });
    expect(within(region).getByText(t('chart.C06.title'), { selector: 'p' })).toBeInTheDocument();
    expect(within(region).getByRole('heading', { name: t('chart.C06.title') })).toBeInTheDocument();
  });

  it('가격 전망: 목표 시점 라디오 3개(쉬운 이름) · 고르면 바뀜 · 판정 개수 줄(서버 verdict 세기)', async () => {
    renderRoute('/compare?ids=2,7,4');
    const region = await screen.findByRole('region', { name: t('page.G4.ladderQ') });
    expect(
      within(region).getByText(`${t('page.G4.ladderHint')} · ${t('page.G4.row.p10Note')}`),
    ).toBeInTheDocument();
    const group = within(region).getByRole('radiogroup', { name: t('page.G4.ladderHorizons') });
    const radios = within(group).getAllByRole('radio');
    expect(radios.map((r) => r.textContent)).toEqual([
      t('chart.C01.horizon.move_in_plus_1y'),
      t('chart.C01.horizon.asof_plus_3y'),
      t('chart.C01.horizon.asof_plus_5y'),
    ]);
    expect(radios[0]).toHaveAttribute('aria-checked', 'true');
    expect(within(region).getByTestId('ladder-verdict-count')).toHaveTextContent(
      t('page.G4.ladderCount', { uncertain: '12', likely: '0', unlikely: '0', total: '12' }),
    );
    await userEvent.click(radios[1] as HTMLElement);
    expect(radios[1]).toHaveAttribute('aria-checked', 'true');
    // 3년 뒤는 모두 review(판정 없음) → 중간 0
    expect(within(region).getByTestId('ladder-verdict-count')).toHaveTextContent(
      t('page.G4.ladderCount', { uncertain: '0', likely: '0', unlikely: '0', total: '12' }),
    );
    expect(region).toHaveTextContent(t('page.G4.row.p10Note'));
  });

  it('verdictCounts: 막대마다 서버 verdict 를 센다(null 은 어느 쪽에도 넣지 않는다)', () => {
    const row = (v: Partial<LadderRow['verdicts']>) =>
      ({ verdicts: { p5: null, p10: null, p20: null, p_flat: null, ...v } }) as LadderRow;
    expect(
      verdictCounts([row({ p5: 'likely', p10: 'uncertain' }), row({ p_flat: 'unlikely' })]),
    ).toEqual({ likely: 1, uncertain: 1, unlikely: 1, total: 8 });
  });

  it('민감도: 질문형 h2 + C10(서버 changed 세기 줄)', async () => {
    renderRoute('/compare?ids=2,7,4');
    const region = await screen.findByRole('region', { name: t('chart.C10.question') });
    expect(within(region).getByText(t('chart.C10.title'), { selector: 'p' })).toBeInTheDocument();
    expect(within(region).getByTestId('c10-summary')).toBeInTheDocument();
    // 같은 화면에서 같은 용어 '?'는 한 번만
    const terms = [...document.querySelectorAll('[data-testid="term"]')].map((el) =>
      el.getAttribute('data-term'),
    );
    expect(new Set(terms).size).toBe(terms.length);
  });

  it('화면 글자에 내부 키(p10·rerank·supported …)가 없다', async () => {
    renderRoute('/compare?ids=2,7,4&scenario=B');
    await screen.findByRole('table', { name: t('page.G4.grid') });
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: t('chart.C10.title') })).toBeInTheDocument(),
    );
    expect(document.body.textContent ?? '').not.toMatch(
      /\b(p10|rerank|benchmark|liquidity|move_in|supported|contradicted)\b/,
    );
  });
});

describe('G4 불러오기 상태(QueryState)', () => {
  it('불러오는 중 → 뼈대 + "불러오는 중…"', async () => {
    server.use(http.get(mswPath('/snapshots/:sid/compare'), () => new Promise(() => {})));
    renderRoute('/compare?ids=2,7,4');
    const box = await screen.findByTestId('skeleton');
    expect(box).toHaveAttribute('role', 'status');
    expect(box).toHaveTextContent(t('app.loading'));
  });

  it('오류 → "불러오지 못했어요" + 다시 시도', async () => {
    let fail = true;
    server.use(
      http.get(mswPath('/snapshots/:sid/compare'), async ({ request }) => {
        if (fail) {
          return HttpResponse.json({ code: 'internal', detail: 'boom' }, { status: 500 });
        }
        const res = await getResponse(generatedHandlers as RequestHandler[], request.clone());
        return HttpResponse.json((await res!.json()) as CompareView);
      }),
    );
    renderRoute('/compare?ids=2,7,4');
    const box = await screen.findByTestId('query-error', {}, { timeout: 10_000 });
    expect(box).toHaveTextContent(
      t('page.common.loadError', { detail: '' }).trim().replace(/:$/, ''),
    );
    fail = false;
    await userEvent.click(within(box).getByRole('button', { name: t('app.retry') }));
    expect(await screen.findByRole('table', { name: t('page.G4.grid') })).toBeInTheDocument();
  }, 20_000);

  it('503 materialize_pending → "준비 중" → 자동으로 다시 불러온다', async () => {
    let calls = 0;
    server.use(
      http.get(mswPath('/snapshots/:sid/compare'), async ({ request }) => {
        calls += 1;
        if (calls === 1) {
          return HttpResponse.json(
            { code: 'materialize_pending', detail: 'x' },
            { status: 503, headers: { 'Retry-After': '0' } },
          );
        }
        const res = await getResponse(generatedHandlers as RequestHandler[], request.clone());
        return HttpResponse.json((await res!.json()) as CompareView);
      }),
    );
    renderRoute('/compare?ids=2,7,4');
    expect(await screen.findByTestId('materialize-pending')).toBeInTheDocument();
    expect(await screen.findByRole('table', { name: t('page.G4.grid') })).toBeInTheDocument();
  });

  it('발행 뒤 만든 내 조건(404) → 안내 + 내 조건 화면 링크', async () => {
    const scenarios = await example<Scenario[]>('/scenarios');
    const base = scenarios.find((s) => s.code === 'base')!;
    server.use(
      http.get(mswPath('/scenarios'), () =>
        HttpResponse.json([
          ...scenarios,
          {
            ...base,
            id: 9,
            code: null,
            is_builtin: false,
            name: '내 9',
            created_at: '2099-01-01T00:00:00+09:00',
          },
        ]),
      ),
      http.get(mswPath('/snapshots/:sid/compare'), () =>
        HttpResponse.json({ code: 'not_found', detail: 'scenario 9' }, { status: 404 }),
      ),
    );
    renderRoute('/compare?ids=2,7,4&scenario=9');
    const box = await screen.findByTestId('scenario-missing');
    expect(
      within(box).getByRole('link', { name: t('page.common.scenarioMissingRun') }),
    ).toHaveAttribute('href', expect.stringMatching(/^\/scenario\?.*scenario=9/));
  });
});
