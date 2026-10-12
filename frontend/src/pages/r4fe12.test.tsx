/**
 * R4 FE12 — 계약 2026-10-09.18 FE 차이 표(`contracts/CHANGELOG.md` .18 F1–F4) 화면 맞춤.
 *  - F1(D23-2): 경쟁률 `type_code` = 읽기 시점 표시 주택형(겹치면 원 코드) — 같은 회차·같은 코드 두 행이 더는 오지 않는다.
 *    화면 변경 없음 → 회귀 고정(원 코드 '84.9582' 행과 '84A' 행이 같은 회차에 따로 보인다, 화면이 코드를 고치지 않는다)
 *  - F2(D23-4): G7 소스 상태 — 청약홈 API 빈 데이터셋 실패 행(`http_status` **200** · `reason`/`last_error_text`
 *    `empty_dataset: totalCount 0`). 2xx 실패라 '확인 불가(200, 날짜)'가 아니라 사유 문자열('확인 불가(빈 데이터셋 — 청약홈
 *    적재 중, 날짜)'). 영문 코드는 화면 문구로 내지 않는다(원 코드는 title 로만)
 *  - F3(D23-4): `region.bootstrap`·`collect.daily` 의 빈 데이터셋 지연 재큐잉(`queued` + stats `requeue_count`·`not_before`·
 *    `requeue_reason` 'degraded_source: …', `degraded_sources`) = 진행 중(실패 아님) — 발행 busy 문구('같은 리비전의 다른
 *    발행…')가 아니라 '불완전한 수집 — 발행하지 않고 다시 수집(n/6회, 시각 이후)'. 6회 넘어 `failed`('degraded_source: …')는
 *    코드 접두 없이. bootstrap 재큐잉 동안 지역 `status` = bootstrapping → 화면 '적재 중'(발행 리비전 없음)
 *  - F4(D23-3): 재정규화 뒤에도 compare 채택·병기 사유가 그대로 — 화면 변경 없음 → 회귀 고정('확인됨' 값 그대로)
 */
import { screen, within } from '@testing-library/react';
import { getResponse, http, HttpResponse, type RequestHandler } from 'msw';
import { requeueInfo, DEGRADED_RETRY_MAX } from '@/api/jobWatch';
import type { ComplexDetail, Fact, JobRun, Region, SourceStatus } from '@/api/types';
import { FactCell, JobProgressView } from '@/components';
import { t } from '@/i18n';
import { kstDateTime } from '@/lib/format';
import { generatedHandlers } from '@/mocks/handlers.gen';
import { resetMockState } from '@/mocks/handlers.extra';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { renderRoute, renderWithProviders } from '@/test/render';

vi.mock('@/charts/EChartRuntime', () => ({ default: () => null }));
beforeEach(() => resetMockState());

async function example<T>(path: string): Promise<T> {
  const res = await getResponse(
    generatedHandlers as RequestHandler[],
    new Request(`http://localhost/api${path}`),
  );
  return (await res?.json()) as T;
}

const EMPTY = 'empty_dataset: totalCount 0';
/** 서버 `collect.EMPTY_DATASET_REASON` + ' n건'(수집 결과 degraded['applyhome']) */
const EMPTY_REASON = '청약홈 API 빈 데이터셋(조건 없는 totalCount 0 — 재적재 중) 3건';
const NOT_BEFORE = '2026-10-13T01:30:00+09:00';

function job(
  id: number,
  jobName: JobRun['job_name'],
  status: JobRun['status'],
  stats: Record<string, unknown> = {},
  errorText: string | null = null,
): JobRun {
  return {
    id,
    job_name: jobName,
    kind: 'manual',
    payload: { region_id: 1 },
    scheduled_at: '2026-10-13T00:10:00+09:00',
    started_at: status === 'queued' ? null : '2026-10-13T00:10:01+09:00',
    finished_at: status === 'done' || status === 'failed' ? '2026-10-13T03:40:00+09:00' : null,
    status,
    stats,
    error_text: errorText,
    progress: null,
  };
}

/** 서버 `handlers._retry_degraded` 가 남기는 bootstrap 재큐잉 stats(daily 아래 degraded_sources) */
const bootstrapRequeued = job(701, 'region.bootstrap', 'queued', {
  region_id: 1,
  snapshot_id: 40,
  daily: { degraded_sources: { applyhome: EMPTY_REASON } },
  requeue_count: 2,
  requeue_reason: `degraded_source: region.bootstrap: applyhome ${EMPTY_REASON} — 발행하지 않고 재시도`,
  not_before: NOT_BEFORE,
});

/** collect.daily 재큐잉 — degraded_sources 가 stats 바로 아래 */
const dailyRequeued = job(702, 'collect.daily', 'queued', {
  degraded_sources: { applyhome: EMPTY_REASON },
  requeue_count: 1,
  requeue_reason: `degraded_source: collect.daily: applyhome ${EMPTY_REASON} — 발행하지 않고 재시도`,
  not_before: NOT_BEFORE,
});

const bootstrapFailed = job(
  703,
  'region.bootstrap',
  'failed',
  { requeue_count: 6 },
  `degraded_source: region.bootstrap: applyhome ${EMPTY_REASON} — 재시도 6회 뒤에도 그대로`,
);

// ─── F1 경쟁률 표시 주택형 ─────────────────────────────────

describe('F1(D23-2) 경쟁률 type_code = 표시 주택형(화면 변경 없음 — 회귀 고정)', () => {
  it('같은 회차의 웹 84A 행과 API 원 코드 84.9582 행이 각각 한 줄 — 화면이 코드를 합치거나 고치지 않는다', async () => {
    const detail = await example<ComplexDetail>('/complexes/2');
    const base = detail.competition[0]!;
    const rows = [
      { ...base, id: 91, round: '1순위', kind: '본청약' as const, type_code: '84A' },
      { ...base, id: 92, round: '1순위', kind: '본청약' as const, type_code: '84.9582' },
      {
        ...base,
        id: 93,
        round: '1순위',
        kind: '본청약' as const,
        type_code: '확인 불가(타입 모호)',
      },
    ];
    server.use(
      http.get(mswPath('/complexes/:id'), () =>
        HttpResponse.json({ ...detail, competition: rows }),
      ),
    );
    renderRoute('/complexes/2#events');
    const section = await screen.findByRole('region', { name: t('page.G3.competition.title') });
    const body = within(section).getAllByRole('row').slice(1);
    expect(body).toHaveLength(3);
    expect(body.map((r) => within(r).getAllByRole('cell')[2]!.textContent)).toEqual([
      '84A',
      '84.9582',
      '확인 불가(타입 모호)',
    ]);
  });
});

// ─── F2 빈 데이터셋 실패 행 ────────────────────────────────

function sources(): SourceStatus[] {
  return [
    {
      source_kind: 'applyhome_list',
      enabled: true,
      disabled_reason: null,
      last_attempt_at: '2026-10-13T00:12:00+09:00',
      last_success_at: '2026-10-12T06:00:00+09:00',
      attempts_7d: 30,
      successes_7d: 28,
      failures_7d: 2,
      last_http_status: 200,
      last_error_text: EMPTY,
      failing_targets: [
        {
          url: 'https://api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1/getAPTLttotPblancDetail',
          complex_id: null,
          complex_name: null,
          http_status: 200,
          reason: EMPTY,
          fetched_at: '2026-10-12T15:12:00Z',
          raw_document_id: 812,
        },
      ],
      retry: { job_name: 'collect.daily', payload: { region_id: 1, sources: ['applyhome'] } },
    },
    {
      source_kind: 'official_site',
      enabled: true,
      disabled_reason: null,
      last_attempt_at: '2026-10-08T06:09:30+09:00',
      last_success_at: '2026-10-08T06:09:12+09:00',
      attempts_7d: 98,
      successes_7d: 70,
      failures_7d: 28,
      last_http_status: 403,
      last_error_text: null,
      failing_targets: [
        {
          url: 'https://opus-switzen.com/',
          complex_id: 4,
          complex_name: '오퍼스 한강 스위첸',
          http_status: 403,
          reason: '403',
          fetched_at: '2026-10-08T06:09:30+09:00',
          raw_document_id: 9231,
        },
      ],
      retry: null,
    },
  ];
}

describe("F2(D23-4) 청약홈 빈 데이터셋 실패 행 — '확인 불가(200, 날짜)'가 아니라 사유", () => {
  async function sourceRow(name: string): Promise<HTMLElement> {
    server.use(http.get(mswPath('/ops/sources'), () => HttpResponse.json(sources())));
    renderRoute('/ops');
    const table = await screen.findByRole('table', { name: t('page.G7.sources') });
    const header = await within(table).findByRole('rowheader', { name: new RegExp(name) });
    return header.closest('tr') as HTMLElement;
  }

  it("실패 대상: '확인 불가(빈 데이터셋 — 청약홈 적재 중, 2026-10-13)' — 200·영문 코드 없이, 날짜는 KST", async () => {
    const row = await sourceRow(t('page.G7.sourceKind.applyhome_list'));
    const item = within(row).getByRole('listitem');
    expect(item).toHaveTextContent(
      t('empty.unknownWithReasonDate', {
        reason: t('page.G7.src.reason.emptyDataset'),
        date: '2026-10-13',
      }),
    );
    expect(item.textContent).not.toMatch(/확인 불가\(200/);
    expect(item.textContent).not.toMatch(/empty_dataset/);
    // 원 코드는 버리지 않는다(마우스 올림·보조 기술용 title)
    expect(within(item).getByTitle(EMPTY)).toBeInTheDocument();
  });

  it('마지막 오류 칸: 서버 코드 대신 화면 문구(원 코드는 title) · 실패 칸은 강조', async () => {
    const row = await sourceRow(t('page.G7.sourceKind.applyhome_list'));
    const cells = within(row).getAllByRole('cell');
    const error = cells[6]!;
    expect(error).toHaveTextContent(t('page.G7.src.reason.emptyDataset'));
    expect(error.textContent).not.toMatch(/empty_dataset/);
    expect(error).toHaveAttribute('title', EMPTY);
    expect(cells[4]!.className).toMatch(/text-danger/);
  });

  it("4xx 실패 대상은 '확인 불가(403, 날짜)'(계약 source_status 표시 규칙 — 상태 코드를 두 번 쓰지 않는다)", async () => {
    const row = await sourceRow(t('page.G7.sourceKind.official_site'));
    const item = within(row).getByRole('listitem');
    expect(item).toHaveTextContent(
      t('empty.unknownWithReasonDate', { reason: '403', date: '2026-10-08' }),
    );
    expect(item.textContent).not.toMatch(/403 403/);
  });
});

// ─── F3 빈 데이터셋 지연 재큐잉 ─────────────────────────────

describe('F3(D23-4) bootstrap·daily 빈 데이터셋 재큐잉 = 진행 중(발행 busy 와 다른 문구)', () => {
  it('requeueInfo: degraded_source 재큐잉은 kind degraded(n·상한 6·다음 시도·사유) — busy 가 아니다', () => {
    expect(DEGRADED_RETRY_MAX).toBe(6);
    expect(requeueInfo(bootstrapRequeued)).toEqual({
      kind: 'degraded',
      n: 2,
      notBefore: NOT_BEFORE,
      detail: EMPTY_REASON,
    });
    expect(requeueInfo(dailyRequeued)).toEqual({
      kind: 'degraded',
      n: 1,
      notBefore: NOT_BEFORE,
      detail: EMPTY_REASON,
    });
    // degraded_sources 가 없으면 requeue_reason 에서 코드·잡 이름 접두와 꼬리를 뗀 것
    const bare = job(704, 'collect.daily', 'queued', {
      requeue_count: 1,
      requeue_reason: `degraded_source: collect.daily: applyhome ${EMPTY_REASON} — 발행하지 않고 재시도`,
    });
    expect(requeueInfo(bare)).toEqual({
      kind: 'degraded',
      n: 1,
      notBefore: null,
      detail: `applyhome ${EMPTY_REASON}`,
    });
  });

  it('kstDateTime: 시간대 붙은 시각 → KST 날짜·시각(분까지)', () => {
    expect(kstDateTime(NOT_BEFORE)).toBe('2026-10-13 01:30');
    expect(kstDateTime('2026-10-12T16:30:00Z')).toBe('2026-10-13 01:30');
    expect(kstDateTime('2026-10-13T01:30:00')).toBe('2026-10-13 01:30');
    expect(kstDateTime('bad')).toBe('bad');
  });

  it("JobProgressView(G0 bootstrap): '불완전한 수집 — 다시 수집(2/6회, 01:30 이후)' + '적재 중', 발행 busy 문구·영문 코드·오류 줄 없음", () => {
    renderWithProviders(<JobProgressView job={bootstrapRequeued} />);
    const box = screen.getByRole('status');
    const note = within(box).getByTestId('job-requeued');
    expect(note).toHaveAttribute('data-requeue', 'degraded');
    expect(note).toHaveTextContent(
      t('job.requeuedDegraded', {
        detail: EMPTY_REASON,
        n: '2',
        max: '6',
        at: t('job.requeuedAt', { at: '2026-10-13 01:30' }),
      }),
    );
    expect(note).toHaveTextContent(t('job.requeuedDegradedBootstrap'));
    expect(box.textContent).not.toContain(t('job.requeued', { n: '2' }));
    expect(box.textContent).not.toMatch(/degraded_source/);
    expect(within(box).queryByText(/오류: /)).toBeNull();
  });

  it('JobProgressView(collect.daily): 이전 발행 리비전이 그대로 기본이라고 밝힌다', () => {
    renderWithProviders(<JobProgressView job={dailyRequeued} />);
    const note = screen.getByTestId('job-requeued');
    expect(note).toHaveTextContent(t('job.requeuedDegradedDaily'));
    expect(note).not.toHaveTextContent(t('job.requeuedDegradedBootstrap'));
  });

  it('JobProgressView: 6회 넘어 failed(degraded_source) — 코드 접두 없이 멈춘 이유', () => {
    renderWithProviders(<JobProgressView job={bootstrapFailed} />);
    const box = screen.getByRole('status');
    expect(box).toHaveTextContent(
      t('job.degradedFailed', {
        max: '6',
        detail: `applyhome ${EMPTY_REASON} — 재시도 6회 뒤에도 그대로`,
      }),
    );
    expect(box.textContent).not.toMatch(/degraded_source/);
  });

  it('JobProgressView: 발행 busy 재큐잉 문구는 그대로(회귀)', () => {
    const busy = job(705, 'snapshot.publish', 'queued', {
      requeue_count: 3,
      requeue_reason: 'publish_in_progress: 다른 발행(job:949)이 진행 중',
    });
    renderWithProviders(<JobProgressView job={busy} />);
    const note = screen.getByTestId('job-requeued');
    expect(note).toHaveAttribute('data-requeue', 'busy');
    expect(note).toHaveTextContent(t('job.requeued', { n: '3' }));
  });

  it('G7 잡 목록: 재큐잉 잡은 대기 + 재수집 안내(다음 시도 시각), failed 는 코드 접두 없는 사유', async () => {
    server.use(
      http.get(mswPath('/jobs'), () =>
        HttpResponse.json([bootstrapRequeued, dailyRequeued, bootstrapFailed]),
      ),
    );
    renderRoute('/ops');
    const table = await screen.findByRole('table', { name: t('page.G7.queue') });
    const rows = await within(table).findAllByRole('row');
    const byId = (id: number) => rows.find((r) => r.textContent?.includes(`#${String(id)}`))!;
    const boot = byId(701);
    expect(boot).toHaveAttribute('data-status', 'queued');
    expect(within(boot).getByTestId('job-requeued')).toHaveTextContent(
      t('job.requeuedDegraded', {
        detail: EMPTY_REASON,
        n: '2',
        max: '6',
        at: t('job.requeuedAt', { at: '2026-10-13 01:30' }),
      }),
    );
    expect(within(byId(702)).getByTestId('job-requeued')).toHaveTextContent(
      t('job.requeuedDegradedDaily'),
    );
    const failed = byId(703);
    expect(failed).toHaveTextContent(
      t('job.degradedFailed', {
        max: '6',
        detail: `applyhome ${EMPTY_REASON} — 재시도 6회 뒤에도 그대로`,
      }),
    );
    expect(table.textContent).not.toMatch(/degraded_source/);
  });

  it("지역 status bootstrapping(발행 리비전 없음) → 화면 '적재 중' 안내(G1 빈 화면 문구도)", async () => {
    const regions = await example<Region[]>('/regions');
    const loading: Region = { ...regions[0]!, status: 'bootstrapping', latest_snapshot: null };
    server.use(
      http.get(mswPath('/regions'), () => HttpResponse.json([loading])),
      http.get(mswPath('/regions/:id/snapshots'), () => HttpResponse.json([])),
    );
    renderRoute('/');
    const banner = await screen.findByTestId('region-loading-banner');
    expect(banner).toHaveAttribute('data-region-status', 'bootstrapping');
    expect(banner).toHaveTextContent(t('app.regionBootstrapping'));
    expect(await screen.findByText(t('app.noSnapshotBootstrapping'))).toBeInTheDocument();
    expect(screen.queryByText(t('app.noSnapshot'))).toBeNull();
  });

  it("지역 status failed(재시도 상한 초과 등) → '첫 적재 실패' 안내, ready 면 안내 없음", async () => {
    const regions = await example<Region[]>('/regions');
    const failed: Region = { ...regions[0]!, status: 'failed', latest_snapshot: null };
    server.use(
      http.get(mswPath('/regions'), () => HttpResponse.json([failed])),
      http.get(mswPath('/regions/:id/snapshots'), () => HttpResponse.json([])),
    );
    const view = renderRoute('/');
    const banner = await screen.findByTestId('region-loading-banner');
    expect(banner).toHaveAttribute('data-region-status', 'failed');
    expect(banner).toHaveTextContent(t('app.regionFailed'));
    view.unmount();

    server.resetHandlers();
    renderRoute('/');
    await screen.findByRole('heading', { name: t('page.G1.title') });
    expect(screen.queryByTestId('region-loading-banner')).toBeNull();
  });
});

// ─── F4 compare 채택 표식 보존 ─────────────────────────────

describe('F4(D23-3) compare 채택·병기 사유는 재정규화 뒤에도 그대로(화면 변경 없음 — 회귀 고정)', () => {
  it("'확인됨' + '판정기 compare 채택 …' 사유 Fact 는 값 그대로(확인 불가로 바꾸지 않는다)", () => {
    const fact = {
      v: 512_000_000,
      label: '확인됨',
      reason: '판정기 compare 채택 jl_abc123 (병기)',
      prov: 'fp_1',
      checked_at: '2026-10-13',
      unit: 'won',
    } as Fact;
    renderWithProviders(<FactCell fact={fact} unit="won" />);
    expect(screen.queryByText(/확인 불가/)).toBeNull();
    expect(screen.getByText(/5억/)).toBeInTheDocument();
  });
});
