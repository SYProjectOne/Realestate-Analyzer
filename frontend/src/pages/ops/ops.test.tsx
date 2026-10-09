import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { t } from '@/i18n';
import { resetMockState } from '@/mocks/handlers.extra';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { renderRoute } from '@/test/render';
import { matching, recordRequests } from '../_shared/testing';
import { since30 } from './JudgmentStatsPanel';

vi.mock('echarts-for-react', () => ({ default: () => null }));
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

  it('사람 확인 저장 → 접수 배지 즉시 갱신 + 재판정 제안 토스트 → POST /jobs(rejudge)', async () => {
    const rec = recordRequests();
    renderRoute('/ops');
    const form = await screen.findByRole('form', { name: t('page.G7.human') });
    const complex = within(form).getByLabelText(t('page.G7.hc.complex'));
    await waitFor(() => expect(complex.querySelectorAll('option').length).toBeGreaterThan(1));
    const complexId = (complex.querySelectorAll('option')[1] as HTMLOptionElement).value;
    await userEvent.selectOptions(complex, complexId);
    await userEvent.selectOptions(within(form).getByLabelText(t('page.G7.hc.value')), '가능');
    await userEvent.type(within(form).getByLabelText(t('page.G7.hc.enteredBy')), '운영자');
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
    };
    expect(posted).toMatchObject({
      complex_id: Number(complexId),
      field: 'intake_status',
      value_text: '가능',
      kind: 'phone',
    });

    const toasts = screen.getByRole('region', { name: t('app.notifications') });
    await userEvent.click(within(toasts).getByRole('button', { name: t('page.G7.rejudge') }));
    await waitFor(() => expect(matching(rec.requests, 'POST', '/jobs')).toHaveLength(1));
    const job = (await matching(rec.requests, 'POST', '/jobs')[0]?.body) as {
      job_name: string;
      payload: { complex_ids: number[] };
    };
    expect(job.job_name).toBe('rejudge');
    expect(job.payload.complex_ids).toEqual([Number(complexId)]);
    rec.stop();
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
