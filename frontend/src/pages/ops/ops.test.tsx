import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { CHECKLIST_KINDS, type ChecklistItem } from '@/api/types';
import { t, tDynamic } from '@/i18n';
import { resetMockState } from '@/mocks/handlers.extra';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { renderRoute } from '@/test/render';
import { enumText } from '../_shared';
import { matching, recordRequests } from '../_shared/testing';
import { since30 } from './JudgmentStatsPanel';

vi.mock('@/charts/EChartRuntime', () => ({ default: () => null }));
beforeEach(() => resetMockState());

describe('G7 데이터·운영', () => {
  it('since30: 기준일 30일 전', () => {
    expect(since30('2026-10-08')).toBe('2026-09-08');
  });

  it('소스 상태 · 큐 · 체크리스트 · 캘린더 · 판정기 통계(30일)', async () => {
    const rec = recordRequests();
    renderRoute('/ops');
    expect(await screen.findByRole('table', { name: t('page.G7.sources') })).toBeInTheDocument();
    expect(await screen.findByRole('table', { name: t('page.G7.queue') })).toBeInTheDocument();
    expect(await screen.findByRole('table', { name: t('page.G7.checklist') })).toBeInTheDocument();
    expect(await screen.findByRole('list', { name: t('page.G7.stat.byTool') })).toBeInTheDocument();
    await waitFor(() =>
      expect(
        matching(rec.requests, 'GET', '/ops/judgments')[0]?.url.searchParams.get('since'),
      ).toBeTruthy(),
    );
    rec.stop();
  });

  it('소스 재시도 버튼 → POST /jobs(retry 잡)', async () => {
    const rec = recordRequests();
    renderRoute('/ops');
    const table = await screen.findByRole('table', { name: t('page.G7.sources') });
    const retry = within(table).getAllByRole('button', {
      name: t('page.G7.src.retry'),
    })[0] as HTMLElement;
    await userEvent.click(retry);
    await waitFor(() => expect(matching(rec.requests, 'POST', '/jobs')).toHaveLength(1));
    const body = (await matching(rec.requests, 'POST', '/jobs')[0]?.body) as { job_name: string };
    expect(body.job_name).toMatch(/^collect\./);
    rec.stop();
  });

  it('사람 확인 저장 → 접수 배지 즉시 갱신 + 자동 등록 재판정(rejudge_job_id) 진행 — POST /jobs 없음(계약 .9)', async () => {
    const rec = recordRequests();
    renderRoute('/ops');
    const form = await screen.findByRole('form', { name: t('page.G7.human') });
    const complex = within(form).getByLabelText(t('page.G7.hc.complex'));
    await waitFor(() => expect(complex.querySelectorAll('option').length).toBeGreaterThan(1));
    const complexId = (complex.querySelectorAll('option')[1] as HTMLOptionElement).value;
    await userEvent.selectOptions(complex, complexId);
    await userEvent.selectOptions(within(form).getByLabelText(t('page.G7.hc.value')), '가능');
    await userEvent.selectOptions(within(form).getByLabelText(t('page.G7.hc.enteredBy')), '운영자');
    await userEvent.click(within(form).getByRole('button', { name: t('page.G7.hc.submit') }));

    const result = await within(form).findByTestId('human-check-result');
    expect(within(result).getByTestId('intake-badge')).toHaveTextContent(t('intake.status.가능'));
    expect(within(result).getByTestId('intake-badge')).toHaveTextContent(
      t('intake.path.human_check'),
    );
    const posted = (await matching(rec.requests, 'POST', '/ops/human-checks')[0]?.body) as {
      complex_id: number;
      field: string;
      value_text: string;
      kind: string;
      entered_by: string;
    };
    expect(posted).toMatchObject({
      complex_id: Number(complexId),
      field: 'intake_status',
      value_text: '가능',
      kind: 'phone',
      entered_by: '운영자',
    });

    // 계약 .9 D12-5: 서버가 재판정 잡을 자동 등록 → 화면은 그 잡 진행만(suggested_job 을 다시 POST 하지 않는다)
    const jobBox = await within(form).findByTestId('human-check-job');
    expect(await within(jobBox).findByText(t('job.title'))).toBeInTheDocument();
    await waitFor(() =>
      expect(matching(rec.requests, 'GET', /\/jobs\/\d+$/).length).toBeGreaterThan(0),
    );
    const toasts = screen.getByRole('region', { name: t('app.notifications') });
    expect(within(toasts).queryByRole('button', { name: t('page.G7.rejudge') })).toBeNull();
    expect(matching(rec.requests, 'POST', '/jobs')).toHaveLength(0);
    rec.stop();
  });

  it('minor 15: 입력자는 역할 select(운영자·검토자)뿐 — 자유 입력 칸 없음', async () => {
    renderRoute('/ops');
    const form = await screen.findByRole('form', { name: t('page.G7.human') });
    const enteredBy = within(form).getByLabelText(t('page.G7.hc.enteredBy'));
    expect(enteredBy.tagName).toBe('SELECT');
    const values = Array.from(enteredBy.querySelectorAll('option'))
      .map((o) => (o as HTMLOptionElement).value)
      .filter(Boolean);
    expect(values).toEqual(['운영자', '검토자']);
    expect(
      within(enteredBy).getByRole('option', { name: t('page.G7.hcRole.검토자') }),
    ).toBeTruthy();
  });

  it('필수값 없이 저장하면 막는다', async () => {
    const rec = recordRequests();
    renderRoute('/ops');
    const form = await screen.findByRole('form', { name: t('page.G7.human') });
    await userEvent.click(within(form).getByRole('button', { name: t('page.G7.hc.submit') }));
    expect(await within(form).findByText(t('page.G7.hc.required'))).toBeInTheDocument();
    expect(matching(rec.requests, 'POST', '/ops/human-checks')).toHaveLength(0);
    rec.stop();
  });

  it('판정기 degraded → 전역 배너', async () => {
    server.use(
      http.get(mswPath('/health'), () =>
        HttpResponse.json({
          status: 'degraded',
          contract_version: '2026-10-09.1',
          app_version: '0.1.0',
          db: 'ok',
          judge: 'degraded',
          time: '2026-10-08T09:00:00+09:00',
        }),
      ),
    );
    renderRoute('/ops');
    expect(await screen.findByTestId('degraded-banner')).toHaveTextContent(t('app.degraded'));
  });

  it('DB 장애 → /health 503(같은 Health 본문)도 전역 배너', async () => {
    server.use(
      http.get(mswPath('/health'), () =>
        HttpResponse.json(
          {
            status: 'degraded',
            contract_version: '2026-10-09.3',
            app_version: '0.1.0',
            db: 'error',
            judge: 'unknown',
            time: '2026-10-08T09:00:00+09:00',
          },
          { status: 503 },
        ),
      ),
    );
    renderRoute('/ops');
    expect(await screen.findByTestId('degraded-banner')).toHaveTextContent(t('app.degraded'));
  });
});

describe('D10-3 체크리스트 종류 "사실 재확인"(계약 2026-10-09.6)', () => {
  it('모든 ChecklistItem.kind 에 표시 문구가 있다', () => {
    for (const kind of CHECKLIST_KINDS) {
      expect(tDynamic(`page.G7.checkKind.${kind}`, '')).not.toBe('');
      expect(enumText('page.G7.checkKind', kind)).not.toBe('');
    }
    expect(CHECKLIST_KINDS).toContain('사실 재확인');
  });

  it('"사실 재확인" 항목이 표·캘린더에 종류 배지와 함께 보인다', async () => {
    const item: ChecklistItem = {
      id: 9001,
      complex_id: 11,
      complex_name: '고촌센트럴자이',
      kind: '사실 재확인',
      title: '사실 재확인: 전매제한 기간(검증 모순)',
      due_date: '2026-10-20',
      status: 'open',
      note: null,
    };
    server.use(http.get(mswPath('/ops/checklist'), () => HttpResponse.json([item])));
    renderRoute('/ops');
    const table = await screen.findByRole('table', { name: t('page.G7.checklist') });
    const row = within(table).getByRole('row', { name: /사실 재확인: 전매제한 기간/ });
    expect(within(row).getByText(t('page.G7.checkKind.사실 재확인'))).toBeInTheDocument();
    const calendar = await screen.findByRole('list', { name: t('page.G7.calendar') });
    expect(within(calendar).getByText(t('page.G7.checkKind.사실 재확인'))).toBeInTheDocument();
  });
});

describe('R9-UI 피드백: G7 캘린더 종류 글자를 쉬운 말로(근거는 둘째 줄·title)', () => {
  const base: ChecklistItem = {
    id: 9001,
    complex_id: 12,
    complex_name: '두산위브 더센트럴 도화',
    kind: '만료',
    title: '전매제한 종료(당첨자 발표일 + 12개월, 산술)',
    due_date: '2026-12-09',
    status: 'open',
    note: null,
  };

  it("전매제한 종료 '만료' → '전매 가능 시작' + 계산 기준 줄, 다른 '만료'는 '기한 만료', 범례", async () => {
    server.use(
      http.get(mswPath('/ops/checklist'), () =>
        HttpResponse.json([
          base,
          {
            ...base,
            id: 9002,
            complex_id: null,
            complex_name: null,
            title: '토지거래허가구역 지정 만료',
          },
          {
            ...base,
            id: 9003,
            kind: '중도금',
            title: '중도금 3회차 납부일',
            due_date: '2027-02-10',
          },
          {
            ...base,
            id: 9004,
            kind: '중도금',
            title: '중도금 3회차 납부일',
            due_date: '2027-02-10',
            note: '84B',
          },
        ]),
      ),
    );
    renderRoute('/ops');
    const calendar = await screen.findByRole('list', { name: t('page.G7.calendar') });
    const resale = within(calendar).getByText(t('page.common.scheduleKind.resaleOpen'));
    const item = resale.closest('li') as HTMLElement;
    expect(item).toHaveAttribute('title', base.title);
    expect(
      within(item).getByText(
        t('page.common.scheduleBasis', { basis: '당첨자 발표일 + 12개월, 산술' }),
      ),
    ).toBeInTheDocument();
    expect(within(calendar).getByText(t('page.common.scheduleKind.만료'))).toBeInTheDocument();
    expect(within(calendar).queryByText(t('page.G7.checkKind.만료'), { exact: true })).toBeNull();
    // 같은 날 같은 제목 두 줄은 숨기지 않는다 — 구별되는 값(메모)이 있으면 보인다
    expect(within(calendar).getAllByText(/중도금 3회차 납부일/)).toHaveLength(2);
    expect(within(calendar).getByText('84B')).toBeInTheDocument();
    const legend = screen.getByTestId('calendar-legend');
    expect(legend).toHaveTextContent(t('page.common.scheduleKind.resaleOpen'));
    expect(legend).toHaveTextContent(t('page.G7.calendarLegend.resaleOpen'));
  });
});
