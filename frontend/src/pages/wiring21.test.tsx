/**
 * R10-FOLLOW × 계약 2026-10-09.21 연결(CHANGELOG .21 FE 차이 F1·F2·F4, DECISIONS D29-3).
 * - G1 다가오는 일정·G7 캘린더·체크리스트에 '청약 접수'·'당첨자 발표'(서버 체크리스트 항목 그대로 — 화면이 일정을 만들지 않는다).
 * - G3 경쟁률 표 당첨 가점 칸: 가점 당첨자 없음(미달) / 발표 전 / 가점 미수집을 사유 코드로 나눠 쉬운 말.
 */
import { screen, within } from '@testing-library/react';
import { getResponse, http, HttpResponse, type RequestHandler } from 'msw';
import type { ChecklistItem, Competition, ComplexDetail, Fact } from '@/api/types';
import { t } from '@/i18n';
import { generatedHandlers } from '@/mocks/handlers.gen';
import { resetMockState } from '@/mocks/handlers.extra';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { renderRoute } from '@/test/render';
import { scheduleDetail } from './_shared/schedule';

vi.mock('@/charts/EChartRuntime', () => ({ default: () => null }));
beforeEach(() => resetMockState());

async function example<T>(path: string): Promise<T> {
  const res = await getResponse(
    generatedHandlers as RequestHandler[],
    new Request(`http://localhost/api${path}`),
  );
  return (await res?.json()) as T;
}

describe('F1·F2 청약 접수·당첨자 발표 일정(D29-3)', () => {
  it('G1 다가오는 일정에 청약 접수(어느 순위인지 둘째 줄)·당첨자 발표, 접수일 미수집 안내 없음', async () => {
    renderRoute('/');
    const box = await screen.findByRole('region', { name: t('page.G1.upcoming.title') });
    const items = await within(box).findAllByRole('listitem');
    const apply = items.find((li) => li.getAttribute('data-due') === '2026-10-20');
    const winner = items.find((li) => li.getAttribute('data-due') === '2026-10-27');
    expect(apply).toBeDefined();
    expect(within(apply!).getByTestId('schedule-kind')).toHaveTextContent(
      t('page.common.scheduleKind.청약 접수'),
    );
    expect(within(apply!).getByTestId('schedule-detail')).toHaveTextContent(
      '1순위 청약 접수(해당지역·기타지역)',
    );
    expect(winner).toBeDefined();
    expect(within(winner!).getByTestId('schedule-kind')).toHaveTextContent(
      t('page.common.scheduleKind.당첨자 발표'),
    );
    expect(within(winner!).queryByTestId('schedule-detail')).toBeNull();
    expect(box).not.toHaveTextContent('청약 접수일은 아직');
  });

  it('G7 캘린더·범례·체크리스트 종류 칸에 두 종류', async () => {
    renderRoute('/ops');
    const calendar = await screen.findByRole('list', { name: t('page.G7.calendar') });
    expect(
      within(calendar).getByText('1순위 청약 접수(해당지역·기타지역)', { exact: false }),
    ).toBeInTheDocument();
    const legend = screen.getByTestId('calendar-legend');
    expect(legend).toHaveTextContent(t('page.G7.calendarLegend.kind.청약 접수'));
    expect(legend).toHaveTextContent(t('page.G7.calendarLegend.kind.당첨자 발표'));
    expect(screen.getAllByText(t('page.G7.checkKind.당첨자 발표')).length).toBeGreaterThan(0);
  });

  it('scheduleDetail: 청약 접수만, 종류와 같은 글자뿐인 제목은 없음', () => {
    const item = (kind: ChecklistItem['kind'], title: string) => ({ kind, title });
    expect(scheduleDetail(item('청약 접수', '특별공급 청약 접수'))).toBe('특별공급 청약 접수');
    expect(scheduleDetail(item('청약 접수', '청약 접수'))).toBeNull();
    expect(scheduleDetail(item('당첨자 발표', '당첨자 발표'))).toBeNull();
    expect(scheduleDetail(item('중도금', '중도금 1회차 납부일'))).toBeNull();
  });

  it('잔여·임의 공고 전체 접수 한 칸(제목 "청약 접수")은 둘째 줄 없이 배지만', async () => {
    server.use(
      http.get(mswPath('/ops/checklist'), () =>
        HttpResponse.json([
          {
            id: 9201,
            complex_id: 2,
            complex_name: '엘리프 검단 포레듀',
            kind: '청약 접수',
            title: '청약 접수',
            due_date: '2026-10-16',
            status: 'open',
            note: '자동: 청약홈 청약 일정 2026-10-16~2026-10-17',
          },
        ]),
      ),
    );
    renderRoute('/');
    const box = await screen.findByRole('region', { name: t('page.G1.upcoming.title') });
    const [li] = await within(box).findAllByRole('listitem');
    expect(within(li!).getByTestId('schedule-kind')).toHaveTextContent('청약 접수');
    expect(within(li!).queryByTestId('schedule-detail')).toBeNull();
  });
});

describe('F4 당첨 가점 사유(가점 당첨자 없음·발표 전·가점 미수집)', () => {
  const unknown = (
    reason: string,
    code: Fact['reason_code'],
    prov: string | null = null,
  ): Fact => ({
    v: null,
    label: '확인 불가',
    reason,
    reason_code: code,
    prov,
    checked_at: prov ? '2026-02-01' : null,
  });
  const scores = (f: Fact) => ({
    winning_score_min: f,
    winning_score_max: f,
    winning_score_avg: f,
  });

  async function render(rows: (detail: ComplexDetail) => Competition[]) {
    const detail = await example<ComplexDetail>('/complexes/2');
    server.use(
      http.get(mswPath('/complexes/:id'), () =>
        HttpResponse.json({ ...detail, competition: rows(detail) }),
      ),
    );
    renderRoute('/complexes/2#events');
    return screen.findByRole('region', { name: t('page.G3.competition.title') });
  }

  it('팝업 "-" 이고 미달이면 "가점 당첨자 없음(미달)", 미달이 아니면 "가점제 당첨자 없음", 원 사유는 title', async () => {
    const section = await render((d) => {
      const [a, b, ...rest] = d.competition;
      return [
        {
          ...a!,
          ratio_or_shortfall_text: '(△60)',
          ...scores(unknown('가점 당첨자 없음(미달)', 'no_winner', 'fp_d1')),
        },
        {
          ...b!,
          ratio_or_shortfall_text: '1.50',
          ...scores(unknown("가점 당첨자 없음(청약홈 '-')", 'no_winner', 'fp_d2')),
        },
        ...rest,
      ];
    });
    expect(within(section).getByText(t('page.G3.competition.points'))).toBeInTheDocument();
    const cells = within(section).getAllByTestId('points-reason');
    const texts = cells.map((c) => c.textContent);
    expect(texts).toContain(t('page.G3.competition.noPointWinnersShortfall'));
    expect(texts).toContain(t('page.G3.competition.noPointWinners'));
    expect(cells[0]).toHaveAttribute('title', '가점 당첨자 없음(미달)');
    expect(within(section).queryByText(t('page.G3.competition.pointsMissing'))).toBeNull();
  });

  it('발표 전이면 "발표 전", 미수집 행은 "가점 미수집"', async () => {
    const section = await render((d) => {
      const [a, b, ...rest] = d.competition;
      return [
        { ...a!, ...scores(unknown('발표 전(당첨자 발표 2026-11-05)', 'not_published')) },
        { ...b!, ...scores(unknown('가점 미수집', 'not_collected')) },
        ...rest,
      ];
    });
    const texts = within(section)
      .getAllByTestId('points-reason')
      .map((c) => c.textContent);
    expect(texts).toContain(t('page.G3.competition.pointsBeforeAnnounce'));
    expect(texts).toContain(t('page.G3.competition.pointsNotCollected'));
  });

  it('모두 가점 미수집이면 열 없이 청약홈 안내 줄(예전 그대로)', async () => {
    const section = await render((d) =>
      d.competition.map((c) => ({ ...c, ...scores(unknown('가점 미수집', 'not_collected')) })),
    );
    expect(within(section).getByText(t('page.G3.competition.pointsMissing'))).toBeInTheDocument();
    expect(within(section).queryByTestId('points-reason')).toBeNull();
  });
});
