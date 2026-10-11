/**
 * R3h FE7 1단계 — 8차 리뷰(`docs/design/wp/R3_REVIEW8.md`) FE minor 13·16·17·18·19 (계약 무관).
 *  - m13(D15-7·D16-5): 사용자 입력 시각(checked_at 등)·서버 시각의 날짜 표시는 KST — 앞 10자(UTC 날짜) 자르기 금지.
 *  - m16: done + `publish_in_progress`(published false)는 '발행 막힘'이 아니다 · 감시 사슬 6단계 상한.
 *  - m17: 여러 칸 422 → 모든 칸 오류·detail 을 보인다 · 제출 전 검사는 형식만(브라우저 시계로 미래 판정 안 함).
 *  - m18: G6 지역을 바꾸면 호재 위치 저장 결과·잡 진행을 지운다.
 *  - m19: publish_blocked 사유는 ko.json 문구 + 포맷한 숫자(영문·날 숫자 금지, 규칙 12).
 */
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { getResponse, http, HttpResponse, type RequestHandler } from 'msw';
import { MemoryRouter } from 'react-router';
import { TOKEN_STORAGE_KEY } from '@/api/auth';
import { PUBLISH_CHAIN_MAX, publishPhase } from '@/api/jobWatch';
import type { JobRun, Region, Snapshot } from '@/api/types';
import { toIsoDay } from '@/charts/util';
import { PublishJobProgress } from '@/components';
import { intakeStatusText } from '@/components/IntakeBadge';
import { t } from '@/i18n';
import { formatDate, formatDday, formatUnknown, kstDay } from '@/lib/format';
import { generatedHandlers } from '@/mocks/handlers.gen';
import { resetMockState } from '@/mocks/handlers.extra';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { renderRoute, renderWithProviders } from '@/test/render';
import { matching, recordRequests } from './_shared/testing';
import { checkedAtProblem } from './ops/HumanCheckForm';

vi.mock('@/charts/EChartRuntime', () => ({ default: () => null }));
beforeEach(() => resetMockState());

const nowIso = () => new Date().toISOString();

function job(
  id: number,
  jobName: JobRun['job_name'],
  status: JobRun['status'],
  stats: Record<string, unknown> = {},
  payload: Record<string, unknown> = {},
  errorText: string | null = null,
): JobRun {
  return {
    id,
    job_name: jobName,
    kind: jobName === 'rejudge' ? 'rejudge' : 'manual',
    payload,
    scheduled_at: nowIso(),
    started_at: nowIso(),
    finished_at: status === 'done' || status === 'failed' ? nowIso() : null,
    status,
    stats,
    error_text: errorText,
    progress: null,
  };
}

async function example<T>(path: string): Promise<T> {
  const res = await getResponse(
    generatedHandlers as RequestHandler[],
    new Request(new URL(`/api${path}`, 'http://localhost').toString()),
  );
  return (await res!.json()) as T;
}

// ─── m13 KST 날짜 ───────────────────────────────────────────

describe('m13(D15-7·D16-5) 시각의 날짜 표시는 KST', () => {
  it('kstDay: 시간대가 붙은 시각 → KST 날짜, 날짜·시간대 없는 값은 그대로', () => {
    expect(kstDay('2026-10-09T20:00:00Z')).toBe('2026-10-10');
    expect(kstDay('2026-10-09T14:59:59Z')).toBe('2026-10-09');
    expect(kstDay('2026-10-09T15:00:00z')).toBe('2026-10-10');
    expect(kstDay('2026-10-09t15:00:00.123+00:00')).toBe('2026-10-10');
    expect(kstDay('2026-10-09T10:00:00-05:00')).toBe('2026-10-10');
    expect(kstDay('2026-10-10T08:59:59+09:00')).toBe('2026-10-10');
    expect(kstDay('2026-12-31T15:00:00Z')).toBe('2027-01-01');
    expect(kstDay('2026-10-09')).toBe('2026-10-09');
    expect(kstDay('2026-10-09T20:00:00')).toBe('2026-10-09');
    expect(kstDay('없음')).toBeNull();
  });

  it('formatDate·formatDday·formatUnknown: 2026-10-09T20:00:00Z → 2026-10-10', () => {
    expect(formatDate('2026-10-09T20:00:00Z')).toBe('2026-10-10');
    expect(formatDate('2026-10-09T20:00:00+00:00', '2026-10-09')).toBe(
      `2026-10-10 (${t('unit.dminus', { n: 1 })})`,
    );
    expect(formatDday('2026-10-09T20:00:00Z', '2026-10-10')).toBe(t('unit.dday'));
    expect(formatDate('2026-10-07')).toBe('2026-10-07');
    expect(formatUnknown('스캔', '2026-10-09T20:00:00Z')).toBe(
      t('empty.unknownWithReasonDate', { reason: '스캔', date: '2026-10-10' }),
    );
  });

  it('IntakeBadge 확인 불가 문구의 날짜도 KST', () => {
    const text = intakeStatusText({
      status: '확인 불가',
      path: 'human_check',
      reason: '전화 불통',
      checked_at: '2026-10-09T20:00:00Z',
    } as Parameters<typeof intakeStatusText>[0]);
    expect(text).toContain('2026-10-10');
    expect(text).not.toContain('2026-10-09');
  });

  it('차트 날짜(toIsoDay)도 KST', () => {
    expect(toIsoDay('2026-10-09T20:00:00Z')).toBe('2026-10-10');
    expect(toIsoDay('2026-10')).toBe('2026-10-01');
  });
});

// ─── m16 publish_in_progress · 사슬 상한 ─────────────────────

describe('m16 done + publish_in_progress 는 막힘이 아니다 · 사슬 6단계 상한', () => {
  const base = { snapshot: undefined, watchStart: 1_000, now: 1_000 };
  // 그 자리 발행(region.expand)이 겹친 발행을 만나 done(published false, publish_in_progress) — 먼저 돈 잡이 발행한다
  const expandBusy = job(970, 'region.expand', 'done', {
    published: false,
    contradicted: 0,
    publish_job_id: 970,
    publish_in_progress: 'job:949',
    snapshot_id: 13,
  });

  it('publishPhase: 기다림(리비전 목록이 published 를 보이면 발행됨)', () => {
    expect(publishPhase({ ...base, trigger: expandBusy, last: expandBusy }).kind).toBe('waiting');
    expect(
      publishPhase({
        ...base,
        trigger: expandBusy,
        last: expandBusy,
        snapshot: { id: 13, status: 'published' } as Snapshot,
      }).kind,
    ).toBe('published');
  });

  it('publishPhase: 서버 모양 그대로의 미룸(done, published false, deferred_to)도 막힘이 아니다', () => {
    // backend `_follow_up`: {published: False, deferred_to, publish_job_id: None}
    const deferred = job(
      961,
      'snapshot.publish',
      'done',
      { follow_up: true, published: false, deferred_to: 14, publish_job_id: null },
      { snapshot_id: 14, follow_up: true },
    );
    expect(publishPhase({ ...base, trigger: deferred, last: deferred })).toEqual({
      kind: 'deferred',
      snapshotId: 14,
    });
  });

  it('화면: 막힘 안내 없이 발행 대기 안내', async () => {
    server.use(http.get(mswPath('/jobs/:id'), () => HttpResponse.json(expandBusy)));
    renderWithProviders(
      <MemoryRouter>
        <PublishJobProgress jobId={970} />
      </MemoryRouter>,
    );
    const box = await screen.findByTestId('publish-job');
    await waitFor(() => expect(box).toHaveAttribute('data-phase', 'waiting'));
    expect(within(box).queryByTestId('publish-blocked')).toBeNull();
    expect(within(box).getByTestId('publish-pending')).toBeInTheDocument();
  });

  it(`사슬은 ${PUBLISH_CHAIN_MAX}단계에서 멈추고 그렇다고 알린다(조용히 기다리지 않는다)`, async () => {
    expect(PUBLISH_CHAIN_MAX).toBe(6);
    // 잡 N 은 늘 다음 잡 N+1 을 publish_job_id 로 가리킨다(끝없는 사슬)
    server.use(
      http.get(mswPath('/jobs/:id'), ({ params }) => {
        const id = Number(params.id);
        return HttpResponse.json(
          job(id, id === 100 ? 'rejudge' : 'snapshot.publish', 'done', {
            publish_job_id: id + 1,
            snapshot_id: 13,
          }),
        );
      }),
    );
    const rec = recordRequests();
    renderWithProviders(
      <MemoryRouter>
        <PublishJobProgress jobId={100} />
      </MemoryRouter>,
    );
    const box = await screen.findByTestId('publish-job');
    expect(
      await within(box).findByTestId('publish-capped', {}, { timeout: 8000 }),
    ).toHaveTextContent(t('job.publishChainCapped', { n: String(PUBLISH_CHAIN_MAX) }));
    expect(within(box).queryByTestId('publish-pending')).toBeNull();
    const ids = new Set(
      matching(rec.requests, 'GET', /\/jobs\/\d+$/).map((r) => r.url.pathname.split('/').pop()),
    );
    expect([...ids].sort()).toEqual(['100', '101', '102', '103', '104', '105']);
    rec.stop();
  }, 15_000);
});

// ─── m19 publish_blocked 문구 ───────────────────────────────

describe('m19 publish_blocked 사유는 ko.json 문구 + 포맷한 숫자', () => {
  it('publishPhase: 막힘은 남은 모순 주장 수(숫자)로 — 영문 문구를 만들지 않는다', () => {
    const trigger = job(900, 'rejudge', 'done', { snapshot_id: 13, publish_job_id: 950 });
    const fromSnapshot = publishPhase({
      trigger,
      last: trigger,
      snapshot: { id: 13, status: 'ready', contradicted_claims: 2 } as Snapshot,
      watchStart: 0,
      now: 0,
    });
    expect(fromSnapshot).toEqual({ kind: 'blocked', contradicted: 2, detail: null });
    const done = job(950, 'snapshot.publish', 'done', {
      publish_job_id: 950,
      published: false,
      contradicted: 1234,
    });
    expect(
      publishPhase({ trigger, last: done, snapshot: undefined, watchStart: 0, now: 0 }),
    ).toEqual({ kind: 'blocked', contradicted: 1234, detail: null });
  });

  it('화면: "남은 모순 주장 1,234건" — publish_blocked·contradicted 영문 없음', async () => {
    server.use(
      http.get(mswPath('/jobs/:id'), () =>
        HttpResponse.json(
          job(950, 'snapshot.publish', 'done', {
            publish_job_id: 950,
            published: false,
            contradicted: 1234,
          }),
        ),
      ),
    );
    renderWithProviders(
      <MemoryRouter>
        <PublishJobProgress jobId={950} />
      </MemoryRouter>,
    );
    const blocked = await screen.findByTestId('publish-blocked');
    expect(blocked).toHaveTextContent(t('job.publishBlockedContradicted', { n: '1,234' }));
    expect(blocked.textContent).not.toMatch(/publish_blocked|contradicted/);
  });

  it('화면: 서버 사유(failed publish_blocked: …)는 코드 접두를 떼고 보인다', async () => {
    server.use(
      http.get(mswPath('/jobs/:id'), () =>
        HttpResponse.json(
          job(950, 'snapshot.publish', 'failed', {}, {}, 'publish_blocked: 판정·점수 미완료'),
        ),
      ),
    );
    renderWithProviders(
      <MemoryRouter>
        <PublishJobProgress jobId={950} />
      </MemoryRouter>,
    );
    const blocked = await screen.findByTestId('publish-blocked');
    expect(blocked).toHaveTextContent(t('job.publishBlocked', { detail: '판정·점수 미완료' }));
    expect(blocked.textContent).not.toMatch(/publish_blocked/);
  });
});

// ─── m17 사람 확인 폼 ───────────────────────────────────────

describe('m17 사람 확인 폼: 여러 칸 오류를 모두 · 제출 전 검사는 형식만', () => {
  async function fillForm() {
    const form = await screen.findByRole('form', { name: t('page.G7.human') });
    const complex = within(form).getByLabelText(t('page.G7.hc.complex'));
    await waitFor(() => expect(complex.querySelector('option[value="2"]')).not.toBeNull());
    await userEvent.selectOptions(complex, '2');
    await userEvent.selectOptions(within(form).getByLabelText(t('page.G7.hc.value')), '가능');
    await userEvent.selectOptions(within(form).getByLabelText(t('page.G7.hc.enteredBy')), '운영자');
    return form;
  }

  it('checkedAtProblem: 브라우저 시계와 무관(먼 미래도 형식이 맞으면 통과)', () => {
    expect(checkedAtProblem('2099-01-01T00:00')).toBeNull();
    expect(checkedAtProblem('')).toBe(t('page.G7.hc.checkedAtRequired'));
    expect(checkedAtProblem('1999-12-31T10:00')).toBe(t('page.G7.hc.checkedAtTooOld'));
  });

  it('미래 확인 시각도 보낸다 — 미래 여부는 서버 code(checked_at_future)로', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-write');
    const detail = 'server says future';
    server.use(
      http.post(mswPath('/ops/human-checks'), () =>
        HttpResponse.json(
          {
            code: 'checked_at_future',
            detail,
            field_errors: [{ loc: ['body', 'checked_at'], msg: detail }],
          },
          { status: 422 },
        ),
      ),
    );
    const rec = recordRequests();
    renderRoute('/ops');
    const form = await fillForm();
    const checkedAt = within(form).getByLabelText(t('page.G7.hc.checkedAt'));
    await userEvent.clear(checkedAt);
    await userEvent.type(checkedAt, '2099-01-01T00:00');
    await userEvent.click(within(form).getByRole('button', { name: t('page.G7.hc.submit') }));
    await waitFor(() =>
      expect(matching(rec.requests, 'POST', '/ops/human-checks')).toHaveLength(1),
    );
    expect(
      await within(form).findByText(t('page.G7.hc.checkedAtFuture', { detail })),
    ).toHaveAttribute('role', 'alert');
    rec.stop();
  });

  it('서버 422 여러 칸: 확인 시각·값·메모 칸 오류와 detail 을 모두 보인다', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-write');
    const detail = '입력 3칸이 잘못됐다';
    server.use(
      http.post(mswPath('/ops/human-checks'), () =>
        HttpResponse.json(
          {
            code: 'validation_error',
            detail,
            field_errors: [
              { loc: ['body', 'checked_at'], msg: 'checked_at bad' },
              { loc: ['body', 'value_text'], msg: 'value bad' },
              { loc: ['body', 'note'], msg: 'note bad' },
              { loc: ['body', 'extra_thing'], msg: 'extra bad' },
            ],
          },
          { status: 422 },
        ),
      ),
    );
    renderRoute('/ops');
    const form = await fillForm();
    await userEvent.click(within(form).getByRole('button', { name: t('page.G7.hc.submit') }));
    const checkedAt = within(form).getByLabelText(t('page.G7.hc.checkedAt'));
    await waitFor(() => expect(checkedAt).toHaveAttribute('aria-invalid', 'true'));
    expect(checkedAt).toHaveAccessibleDescription(
      t('page.G7.hc.checkedAtServer', { detail: 'checked_at bad' }),
    );
    const value = within(form).getByLabelText(t('page.G7.hc.value'));
    expect(value).toHaveAttribute('aria-invalid', 'true');
    expect(value).toHaveAccessibleDescription('value bad');
    const note = within(form).getByLabelText(t('page.G7.hc.note'));
    expect(note).toHaveAttribute('aria-invalid', 'true');
    expect(note).toHaveAccessibleDescription('note bad');
    const general = within(form).getByTestId('hc-server-error');
    expect(general).toHaveTextContent(detail);
    expect(general).toHaveTextContent('extra bad');
  });

  it('서버 422 checked_at_future + 다른 칸(entered_by) → 둘 다', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-write');
    server.use(
      http.post(mswPath('/ops/human-checks'), () =>
        HttpResponse.json(
          {
            code: 'checked_at_future',
            detail: 'two problems',
            field_errors: [
              { loc: ['body', 'checked_at'], msg: 'too far' },
              { loc: ['body', 'entered_by'], msg: 'role bad' },
            ],
          },
          { status: 422 },
        ),
      ),
    );
    renderRoute('/ops');
    const form = await fillForm();
    await userEvent.click(within(form).getByRole('button', { name: t('page.G7.hc.submit') }));
    expect(
      await within(form).findByText(t('page.G7.hc.checkedAtFuture', { detail: 'too far' })),
    ).toBeInTheDocument();
    expect(within(form).getByLabelText(t('page.G7.hc.enteredBy'))).toHaveAccessibleDescription(
      'role bad',
    );
    expect(within(form).getByTestId('hc-server-error')).toHaveTextContent('two problems');
  });

  it('제출 전 검사도 여러 칸을 한 번에(값 형식 + 확인 시각 비어 있음)', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-write');
    const rec = recordRequests();
    renderRoute('/ops');
    const form = await screen.findByRole('form', { name: t('page.G7.human') });
    const complex = within(form).getByLabelText(t('page.G7.hc.complex'));
    await waitFor(() => expect(complex.querySelector('option[value="2"]')).not.toBeNull());
    await userEvent.selectOptions(complex, '2');
    await userEvent.selectOptions(
      within(form).getByLabelText(t('page.G7.hc.field')),
      'resale_months',
    );
    await userEvent.type(within(form).getByLabelText(t('page.G7.hc.value')), '6.02');
    await userEvent.selectOptions(within(form).getByLabelText(t('page.G7.hc.enteredBy')), '운영자');
    await userEvent.clear(within(form).getByLabelText(t('page.G7.hc.checkedAt')));
    await userEvent.click(within(form).getByRole('button', { name: t('page.G7.hc.submit') }));
    expect(await within(form).findByText(t('page.G7.hc.badInt'))).toBeInTheDocument();
    expect(within(form).getByText(t('page.G7.hc.checkedAtRequired'))).toHaveAttribute(
      'role',
      'alert',
    );
    expect(matching(rec.requests, 'POST', '/ops/human-checks')).toHaveLength(0);
    rec.stop();
  });
});

// ─── m18 G6 지역 변경 ───────────────────────────────────────

describe('m18 G6 지역을 바꾸면 호재 위치 결과·잡 진행을 지운다', () => {
  it('위치 저장 결과(links·잡) · 호재 URL 등록 결과가 다른 지역에 남지 않는다', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-write');
    const regions = await example<Region[]>('/regions');
    const snapshots = await example<Snapshot[]>('/regions/1/snapshots');
    const r1 = regions[0]!;
    const s12 = snapshots[0]!;
    const s22: Snapshot = { ...s12, id: 22, region_id: 2 };
    const r2: Region = { ...r1, id: 2, name: '테스트 지역 둘', latest_snapshot: s22 };
    server.use(
      http.get(mswPath('/regions'), () => HttpResponse.json([r1, r2])),
      http.get(mswPath('/regions/:id/snapshots'), ({ params }) =>
        HttpResponse.json(String(params.id) === '2' ? [s22] : snapshots),
      ),
    );
    renderRoute('/market?region=1');
    const panel = await screen.findByRole('region', { name: t('page.G6.loc.title') });
    const list = within(panel).getByRole('list', { name: t('page.G6.loc.title') });
    const item = (await within(list).findByText('GTX-B')).closest('li') as HTMLElement;
    await userEvent.click(within(item).getByRole('button', { name: t('page.G6.loc.open') }));
    const form = within(item).getByRole('form', {
      name: t('page.G6.loc.formFor', { name: 'GTX-B' }),
    });
    const select = within(form).getByLabelText(t('page.G6.loc.complexes'));
    await waitFor(() => expect(select.querySelectorAll('option').length).toBeGreaterThan(1));
    await userEvent.selectOptions(
      select,
      (select.querySelectorAll('option')[0] as HTMLOptionElement).value,
    );
    await userEvent.click(within(form).getByRole('button', { name: t('page.G6.loc.submit') }));
    expect(await screen.findByTestId('catalyst-job')).toBeInTheDocument();

    const urlForm = await screen.findByRole('form', { name: t('page.G6.catalyst.title') });
    await userEvent.type(
      within(urlForm).getByLabelText(t('page.G6.catalyst.url')),
      'https://www.example-news.kr/a/1',
    );
    await userEvent.type(
      within(urlForm).getByLabelText(t('page.G6.catalyst.titleField')),
      '새 호재',
    );
    await userEvent.click(
      within(urlForm).getByRole('button', { name: t('page.G6.catalyst.submit') }),
    );
    expect(await screen.findByTestId('catalyst-created')).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText(t('header.region')), '2');
    await screen.findByRole('region', { name: t('page.G6.loc.title') });
    await waitFor(() => expect(screen.queryByTestId('catalyst-links')).toBeNull());
    expect(screen.queryByTestId('catalyst-job')).toBeNull();
    expect(screen.queryByTestId('catalyst-created')).toBeNull();
    expect(screen.queryByTestId('publish-job')).toBeNull();
  });
});
