/**
 * R3g FE6 2단계 — 계약 2026-10-09.12 FE 차이 표(`contracts/CHANGELOG.md` .12) 화면 맞춤:
 *  - F1(D15-2): `rd_` 출처도 늘 snapshot_id 를 넘긴다(`provenanceSnapshot` 예외 제거).
 *  - F3: POST /catalysts 201 `job_id`(rejudge) — 발행까지 감시.
 *  - F4·F12·F15(7차 minor 19): 발행 안내는 잡 stats `publish_job_id` 를 이어 감시해 발행 잡이 끝날 때 닫는다
 *    (후속 잡 포함·미룸 `deferred_to`·`publish_in_progress`), publish_blocked·실패·30분 상한은 알린다. 잡 목록 뒤지기 없음.
 *  - F8·F14(7차 minor 20): checked_at 422 는 code 3종으로 가른다(서버 문구·브라우저 시계로 추측하지 않는다).
 *    입력 단계에서 KST 2000-01-01 이전도 막는다.
 */
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { MemoryRouter } from 'react-router';
import { TOKEN_STORAGE_KEY } from '@/api/auth';
import { ApiError } from '@/api/client';
import { provenanceSnapshot } from '@/api/hooks';
import {
  nextPublishJobId,
  PUBLISH_FOLLOW_MAX_MS,
  publishPhase,
  publishTarget,
} from '@/api/jobWatch';
import type { JobRun, Snapshot } from '@/api/types';
import { PublishJobProgress } from '@/components';
import { t } from '@/i18n';
import { resetMockState } from '@/mocks/handlers.extra';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { renderRoute, renderWithProviders } from '@/test/render';
import { matching, recordRequests } from './_shared/testing';
import { checkedAt422Kind, checkedAtProblem } from './ops/HumanCheckForm';

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

// ─── F1 ────────────────────────────────────────────────────

describe('F1(D15-2) rd_ 출처도 늘 snapshot_id 를 넘긴다', () => {
  it('provenanceSnapshot: 예외 없음', () => {
    expect(provenanceSnapshot('rd_9062', '12')).toBe('12');
    expect(provenanceSnapshot('fp_11', 12)).toBe(12);
    expect(provenanceSnapshot('rd_9062', null)).toBeNull();
    expect(provenanceSnapshot(null, '12')).toBeNull();
  });
});

// ─── F3 ────────────────────────────────────────────────────

describe('F3 POST /catalysts 201 job_id → 발행까지 감시', () => {
  it('호재 URL 저장 → job_id(rejudge) 를 발행 대기 안내와 함께 감시', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-write');
    renderRoute('/market');
    const f = await screen.findByRole('form', { name: t('page.G6.catalyst.title') });
    await userEvent.type(
      within(f).getByLabelText(t('page.G6.catalyst.url')),
      'https://www.example-news.kr/a/1',
    );
    await userEvent.type(within(f).getByLabelText(t('page.G6.catalyst.titleField')), '새 호재');
    await userEvent.click(within(f).getByRole('button', { name: t('page.G6.catalyst.submit') }));
    const done = await screen.findByTestId('catalyst-created');
    const publish = within(done).getByTestId('publish-job');
    expect(within(publish).getByTestId('publish-pending')).toHaveTextContent(
      t('job.publishPending'),
    );
    expect(await within(publish).findByText('rejudge')).toBeInTheDocument();
  });
});

// ─── F4·F12·F15 ────────────────────────────────────────────

describe('F15 발행 안내는 stats.publish_job_id 를 이어 감시해 닫는다(7차 minor 19)', () => {
  const base = { snapshot: undefined, watchStart: 1_000, now: 1_000 };
  const rejudgeDone = job(900, 'rejudge', 'done', { snapshot_id: 13, publish_job_id: 950 });

  it('nextPublishJobId: 자기와 다른 publish_job_id(재시도 포함)만', () => {
    expect(nextPublishJobId(rejudgeDone)).toBe(950);
    expect(nextPublishJobId(job(950, 'snapshot.publish', 'done', { publish_job_id: 950 }))).toBe(
      null,
    );
    expect(nextPublishJobId(job(970, 'region.expand', 'done', { publish_retry_job_id: 980 }))).toBe(
      980,
    );
    expect(
      nextPublishJobId(
        job(960, 'snapshot.publish', 'done', { included_in_snapshot_id: 13, publish_job_id: 955 }),
      ),
    ).toBe(955);
    expect(nextPublishJobId(job(900, 'rejudge', 'running', { publish_job_id: 950 }))).toBeNull();
    expect(nextPublishJobId(job(900, 'rejudge', 'done'))).toBeNull();
  });

  it('publishTarget: 미룸(deferred_to) → 결과 리비전 → 요청 리비전', () => {
    expect(
      publishTarget(job(1, 'snapshot.publish', 'done', { deferred_to: 14 }, { snapshot_id: 13 })),
    ).toBe(14);
    expect(publishTarget(rejudgeDone)).toBe(13);
    expect(publishTarget(job(2, 'snapshot.publish', 'queued', {}, { snapshot_id: 15 }))).toBe(15);
  });

  it('publishPhase: 잡 사슬의 마지막 잡으로 판단', () => {
    const p = (trigger: JobRun | undefined, last: JobRun | undefined, extra = {}) =>
      publishPhase({ ...base, trigger, last, ...extra });
    expect(p(job(900, 'rejudge', 'running'), undefined).kind).toBe('trigger');
    expect(p(job(900, 'rejudge', 'failed'), job(900, 'rejudge', 'failed')).kind).toBe(
      'triggerFailed',
    );
    // rejudge done → 다음 잡(950)을 아직 못 받았다
    expect(p(rejudgeDone, rejudgeDone).kind).toBe('waiting');
    expect(p(rejudgeDone, job(950, 'snapshot.publish', 'running')).kind).toBe('waiting');
    const published = job(950, 'snapshot.publish', 'done', {
      publish_job_id: 950,
      published: true,
    });
    expect(p(rejudgeDone, published).kind).toBe('published');
    // 그 자리 발행(region.expand) — 자기 자신이 발행 잡
    const expand = job(970, 'region.expand', 'done', { publish_job_id: 970, published: true });
    expect(p(expand, expand).kind).toBe('published');
    // 막힘: done + published false, 또는 failed publish_blocked
    expect(
      p(
        rejudgeDone,
        job(950, 'snapshot.publish', 'done', {
          publish_job_id: 950,
          published: false,
          contradicted: 2,
        }),
      ).kind,
    ).toBe('blocked');
    expect(
      p(
        rejudgeDone,
        job(950, 'snapshot.publish', 'failed', {}, {}, 'publish_blocked: contradicted 2건'),
      ),
    ).toEqual({ kind: 'blocked', contradicted: null, detail: 'contradicted 2건' });
    // F12: 겹친 발행은 먼저 돈 잡이 발행한다 — 리비전 목록이 published 를 보일 때까지 기다린다
    const inProgress = job(
      950,
      'snapshot.publish',
      'failed',
      {},
      { snapshot_id: 13 },
      'publish_in_progress: 잡 949',
    );
    expect(p(rejudgeDone, inProgress).kind).toBe('waiting');
    expect(
      p(rejudgeDone, inProgress, { snapshot: { id: 13, status: 'published' } as Snapshot }).kind,
    ).toBe('published');
    expect(
      p(rejudgeDone, job(950, 'snapshot.publish', 'failed', {}, {}, 'OperationalError')),
    ).toEqual({ kind: 'publishFailed', detail: 'OperationalError' });
    // F4: 후속 잡이 다른 발행에 포함돼 닫힘 → 그 발행 잡(publish_job_id) 을 이어 본다
    const included = job(
      960,
      'snapshot.publish',
      'done',
      { included_in_snapshot_id: 13, publish_job_id: 955 },
      { snapshot_id: 13, follow_up: true },
    );
    expect(p(included, included).kind).toBe('waiting');
    // F4: 판정 중이라 미룸 → 그 리비전이 발행될 때까지
    const deferred = job(
      961,
      'snapshot.publish',
      'done',
      { deferred_to: 14, publish_job_id: null },
      { snapshot_id: 14, follow_up: true },
    );
    expect(p(deferred, deferred)).toEqual({ kind: 'deferred', snapshotId: 14 });
    expect(
      p(deferred, deferred, { snapshot: { id: 14, status: 'published' } as Snapshot }).kind,
    ).toBe('published');
    // 리비전 목록이 먼저 발행을 보이면 닫는다
    expect(
      p(rejudgeDone, rejudgeDone, { snapshot: { id: 13, status: 'published' } as Snapshot }).kind,
    ).toBe('published');
    // 남은 모순 주장으로 ready 에 멈춘 리비전
    expect(
      p(rejudgeDone, rejudgeDone, {
        snapshot: { id: 13, status: 'ready', contradicted_claims: 2 } as Snapshot,
      }).kind,
    ).toBe('blocked');
    // 상한
    expect(p(rejudgeDone, rejudgeDone, { now: 1_000 + PUBLISH_FOLLOW_MAX_MS + 1 }).kind).toBe(
      'expired',
    );
  });

  it('화면: rejudge done → publish_job_id 잡을 이어 감시 → 그 잡 done 이면 "발행됨"(잡 목록 조회 없음)', async () => {
    let publishStatus: JobRun['status'] = 'running';
    server.use(
      http.get(mswPath('/jobs/:id'), ({ params }) => {
        const id = Number(params.id);
        if (id === 900) {
          return HttpResponse.json(
            job(
              900,
              'rejudge',
              'done',
              { snapshot_id: 13, publish_job_id: 950 },
              { snapshot_id: 12 },
            ),
          );
        }
        return HttpResponse.json(
          job(
            950,
            'snapshot.publish',
            publishStatus,
            publishStatus === 'done'
              ? { publish_job_id: 950, published: true, snapshot_id: 13 }
              : {},
            { snapshot_id: 13 },
          ),
        );
      }),
    );
    const rec = recordRequests();
    renderWithProviders(
      <MemoryRouter>
        <PublishJobProgress jobId={900} />
      </MemoryRouter>,
    );
    const box = await screen.findByTestId('publish-job');
    expect(await within(box).findByText('snapshot.publish')).toBeInTheDocument();
    expect(within(box).getByTestId('publish-pending')).toHaveTextContent(t('job.publishPending'));
    publishStatus = 'done';
    expect(await within(box).findByTestId('publish-done', {}, { timeout: 8000 })).toHaveTextContent(
      t('job.publishDone'),
    );
    expect(within(box).queryByTestId('publish-pending')).toBeNull();
    expect(matching(rec.requests, 'GET', /\/jobs$/)).toHaveLength(0);
    rec.stop();
  }, 15_000);

  it('화면: 발행 잡이 publish_blocked 로 실패하면 막힘 안내', async () => {
    const detail = 'publish_blocked: 남은 모순 2건';
    server.use(
      http.get(mswPath('/jobs/:id'), ({ params }) =>
        Number(params.id) === 900
          ? HttpResponse.json(job(900, 'rejudge', 'done', { snapshot_id: 13, publish_job_id: 950 }))
          : HttpResponse.json(
              job(950, 'snapshot.publish', 'failed', {}, { snapshot_id: 13 }, detail),
            ),
      ),
    );
    renderWithProviders(
      <MemoryRouter>
        <PublishJobProgress jobId={900} />
      </MemoryRouter>,
    );
    // 8차 m19: 코드 접두(publish_blocked:)는 떼고 보인다
    expect(await screen.findByTestId('publish-blocked')).toHaveTextContent(
      t('job.publishBlocked', { detail: '남은 모순 2건' }),
    );
    expect(screen.queryByTestId('publish-pending')).toBeNull();
  });

  it('화면: 후속 발행 잡이 미뤄지면(deferred_to) 그 리비전 발행까지 기다린다는 안내', async () => {
    server.use(
      http.get(mswPath('/jobs/:id'), () =>
        HttpResponse.json(
          job(
            961,
            'snapshot.publish',
            'done',
            { deferred_to: 14, publish_job_id: null },
            { snapshot_id: 14, follow_up: true },
          ),
        ),
      ),
    );
    renderWithProviders(
      <MemoryRouter>
        <PublishJobProgress jobId={961} />
      </MemoryRouter>,
    );
    expect(await screen.findByTestId('publish-deferred')).toHaveTextContent(
      t('job.publishDeferred'),
    );
    expect(screen.getByTestId('publish-pending')).toBeInTheDocument();
  });
});

// ─── F8·F14 ────────────────────────────────────────────────

describe('F14 checked_at 422 는 code 로 가른다 · F8 KST 2000-01-01 이전은 입력에서 막는다', () => {
  const err = (code: string, detail = 'x') =>
    new ApiError(code as 'validation_error', detail, 422, [
      { loc: ['body', 'checked_at'], msg: detail },
    ]);

  it('checkedAt422Kind: code 3종, 그 밖 checked_at 오류는 other', () => {
    expect(checkedAt422Kind(err('checked_at_future'))).toBe('future');
    expect(checkedAt422Kind(err('checked_at_before_source'))).toBe('early');
    expect(checkedAt422Kind(err('checked_at_format'))).toBe('format');
    // 문구에 '미래' 가 있어도 code 가 아니면 미래로 보지 않는다(문구 표지 의존 제거)
    expect(checkedAt422Kind(err('validation_error', '지금보다 10분 넘게 미래다'))).toBe('other');
    expect(checkedAt422Kind(new ApiError('validation_error', 'x', 422))).toBeNull();
    expect(checkedAt422Kind(new ApiError('internal', 'x', 500))).toBeNull();
  });

  it('checkedAtProblem: KST 2000-01-01 이전은 범위 안내(보내지 않는다)', () => {
    expect(checkedAtProblem('1999-12-31T10:00')).toBe(t('page.G7.hc.checkedAtTooOld'));
    expect(checkedAtProblem('0001-01-01T00:00')).toBe(t('page.G7.hc.checkedAtTooOld'));
    expect(checkedAtProblem('2000-01-02T00:00')).toBeNull();
  });

  async function submitWith(code: string, detail: string) {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-write');
    server.use(
      http.post(mswPath('/ops/human-checks'), () =>
        HttpResponse.json(
          { code, detail, field_errors: [{ loc: ['body', 'checked_at'], msg: detail }] },
          { status: 422 },
        ),
      ),
    );
    renderRoute('/ops');
    const form = await screen.findByRole('form', { name: t('page.G7.human') });
    const complex = within(form).getByLabelText(t('page.G7.hc.complex'));
    await waitFor(() => expect(complex.querySelector('option[value="2"]')).not.toBeNull());
    await userEvent.selectOptions(complex, '2');
    await userEvent.selectOptions(within(form).getByLabelText(t('page.G7.hc.value')), '가능');
    await userEvent.selectOptions(within(form).getByLabelText(t('page.G7.hc.enteredBy')), '운영자');
    await userEvent.click(within(form).getByRole('button', { name: t('page.G7.hc.submit') }));
    return form;
  }

  it('checked_at_future(문구와 무관) → 미래 안내', async () => {
    const form = await submitWith('checked_at_future', 'server clock ahead');
    expect(
      await within(form).findByText(
        t('page.G7.hc.checkedAtFuture', { detail: 'server clock ahead' }),
      ),
    ).toBeInTheDocument();
  });

  it('checked_at_before_source → 이른 확인일 안내', async () => {
    const form = await submitWith('checked_at_before_source', 'observed later');
    expect(
      await within(form).findByText(
        t('page.G7.hc.checkedAtTooEarly', { detail: 'observed later' }),
      ),
    ).toBeInTheDocument();
  });

  it('checked_at_format → 형식·범위 안내', async () => {
    const form = await submitWith('checked_at_format', 'before 2000');
    expect(
      await within(form).findByText(t('page.G7.hc.checkedAtFormat', { detail: 'before 2000' })),
    ).toBeInTheDocument();
  });
});
