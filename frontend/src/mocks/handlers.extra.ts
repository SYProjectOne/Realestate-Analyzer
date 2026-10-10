/**
 * 수동 보강 핸들러 (WP6a 소유) — 생성물(handlers.gen.ts)에 없거나 예시 하나만으로 부족한 동작.
 * 여기 핸들러가 생성 핸들러보다 **먼저** 매칭된다(handlers.ts 순서).
 *
 * 원칙: 응답 모양은 생성 핸들러(=계약 예시)에서 `getResponse`로 받아 그대로 쓰고, 상태만 덧붙인다.
 *  - 잡: POST /jobs·/reports·/regions·PATCH /regions 가 만든 잡은 GET /jobs/{id} 폴링마다 queued → running → done
 *  - 사람 확인: POST /ops/human-checks 후 단지 목록·상세의 intake가 그 값으로 바뀐다(배지 즉시 갱신),
 *    자동 등록 재판정(rejudge_job_id, 계약 .9)도 상태 있는 잡
 *  - G2 대량 행: localStorage `msw.complexes.rows` = N 이면 예시 행을 N개로 복제(가상 스크롤 확인용)
 *  - 판정기 장애: localStorage `msw.degraded` = 1 이면 /health status=degraded
 *  - 원문 텍스트: GET /raw/{id}?as=text (생성기가 건너뜀), GET /reports/{id}
 *  - 주장 수정 PATCH /claims/{id}·호재 URL POST /catalysts 가 만든 잡도 상태 있는 잡(계약 2026-10-09.4)
 *  - 공유 링크 POST /share-links: 요청 label 을 응답에 반영
 *  - 계약 .10 초안(R3e FE4 — CORE3 머지 뒤 gen:msw 로 맞춤): 단지 상세 `price.discount_applied`,
 *    시장 `?scenario=` 검증
 *  - 계약 .8(리비전·사람 확인 field·PATCH /catalysts·PATCH /regions)은 생성 핸들러(계약 예시)를 그대로 쓴다 — 초안 목 없음.
 *    상태가 필요한 테스트는 server.use 로 개별 덮어쓴다.
 * 지역명은 목 데이터(계약 예시)에만 있다.
 */
import { getResponse, http, HttpResponse, type RequestHandler } from 'msw';
import type {
  CatalystCreate,
  CatalystCreated,
  ClaimPatch,
  ComplexDetail,
  ComplexRow,
  ComplexRowPage,
  Health,
  HumanCheck,
  HumanCheckCreate,
  Intake,
  JobCreate,
  JobName,
  JobRun,
  Market,
  PriceRangeWithApplied,
  Provenance,
  RegionCreated,
  RegionPatched,
  ReportRequest,
  ShareLinkCreate,
  ShareLinkCreated,
} from '@/api/types';
import { generatedHandlers } from './handlers.gen';
import { mswPath } from './mswPath';

export const MOCK_ROWS_KEY = 'msw.complexes.rows';
export const MOCK_DEGRADED_KEY = 'msw.degraded';
/** GET /jobs/{id}를 이 횟수만큼 부르면 done */
export const MOCK_JOB_POLLS_TO_DONE = 2;

function readFlag(key: string): string | null {
  try {
    return globalThis.localStorage?.getItem(key) ?? null;
  } catch {
    return null;
  }
}

/** 같은 요청을 생성 핸들러(계약 예시)에 보내 JSON을 받는다 */
async function base<T>(request: Request, method = 'GET', body?: unknown): Promise<T> {
  const req = new Request(request.url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const res = await getResponse(generatedHandlers as RequestHandler[], req);
  if (!res) throw new Error(`no generated handler: ${method} ${request.url}`);
  return (await res.json()) as T;
}

// ─── 상태 ──────────────────────────────────────────────────

interface MockJob {
  job: JobRun;
  polls: number;
}

const state = {
  nextJobId: 5000,
  jobs: new Map<number, MockJob>(),
  intakeOverrides: new Map<number, Intake>(),
};

/** 테스트 사이 초기화(src/test/setup.ts가 resetHandlers 때 부를 수 있다) */
export function resetMockState(): void {
  state.nextJobId = 5000;
  state.jobs.clear();
  state.intakeOverrides.clear();
}

const nowIso = () => new Date().toISOString();

function registerJob(jobName: JobName, payload: Record<string, unknown>, id?: number): JobRun {
  const jobId = id ?? state.nextJobId++;
  const job: JobRun = {
    id: jobId,
    job_name: jobName,
    kind: jobName === 'rejudge' ? 'rejudge' : 'manual',
    payload,
    scheduled_at: nowIso(),
    started_at: null,
    finished_at: null,
    status: 'queued',
    stats: {},
    error_text: null,
    progress: null,
  };
  state.jobs.set(jobId, { job, polls: 0 });
  return job;
}

function advanceJob(entry: MockJob): JobRun {
  entry.polls += 1;
  const { job } = entry;
  if (entry.polls >= MOCK_JOB_POLLS_TO_DONE) {
    entry.job = {
      ...job,
      status: 'done',
      started_at: job.started_at ?? nowIso(),
      finished_at: nowIso(),
      progress: { done: 1, total: 1, step: null },
    };
  } else {
    entry.job = {
      ...job,
      status: 'running',
      started_at: job.started_at ?? nowIso(),
      progress: { done: entry.polls, total: MOCK_JOB_POLLS_TO_DONE, step: job.job_name },
    };
  }
  return entry.job;
}

function applyIntake<T extends { complex_id: number; intake: Intake | null }>(row: T): T {
  const override = state.intakeOverrides.get(row.complex_id);
  return override ? { ...row, intake: override } : row;
}

// ─── G2 목록 ───────────────────────────────────────────────

function multiplyRows(rows: ComplexRow[], n: number): ComplexRow[] {
  if (rows.length === 0) return rows;
  const out: ComplexRow[] = [];
  for (let i = 0; i < n; i += 1) {
    const src = rows[i % rows.length] as ComplexRow;
    const copy = Math.floor(i / rows.length);
    out.push(
      copy === 0
        ? src
        : { ...src, complex_id: 100_000 + i, name: `${src.name} #${copy + 1}`, rank: null },
    );
  }
  return out;
}

function filterRows(rows: ComplexRow[], url: URL): ComplexRow[] {
  const f = (k: string) => url.searchParams.get(`filter[${k}]`);
  const list = (k: string) => f(k)?.split(',').filter(Boolean) ?? null;
  const livingArea = list('living_area');
  const intake = list('intake_status');
  const land = list('land_type');
  const inclusion = list('inclusion_class');
  const scope = list('judge_scope');
  const q = f('q')?.trim();
  const priceMin = f('price_min');
  const priceMax = f('price_max');
  const moveInYear = f('move_in_year');
  const resaleBefore = f('resale_end_before');
  return rows.filter((r) => {
    if (livingArea && !livingArea.includes(r.living_area ?? '')) return false;
    if (intake && !intake.includes(r.intake?.status ?? '확인 불가')) return false;
    if (land && !land.includes(String(r.land_type.v ?? ''))) return false;
    if (inclusion && !inclusion.includes(r.inclusion_class)) return false;
    if (scope && !scope.includes(r.judge_scope)) return false;
    if (q && !r.name.includes(q)) return false;
    const mid = typeof r.price_mid.v === 'number' ? r.price_mid.v : null;
    if (priceMin && (mid === null || mid < Number(priceMin))) return false;
    if (priceMax && (mid === null || mid > Number(priceMax))) return false;
    if (moveInYear && !String(r.move_in_ym.v ?? '').startsWith(moveInYear)) return false;
    if (resaleBefore && !(String(r.resale_end.v ?? '9999') <= resaleBefore)) return false;
    return true;
  });
}

// ─── 핸들러 ────────────────────────────────────────────────

export const extraHandlers = [
  // GET /health — 판정기 장애 모드
  http.get(mswPath('/health'), async ({ request }) => {
    const health = await base<Health>(request);
    if (readFlag(MOCK_DEGRADED_KEY) === '1') {
      return HttpResponse.json({ ...health, status: 'degraded', judge: 'degraded' });
    }
    return HttpResponse.json(health);
  }),

  // GET /snapshots/{sid}/complexes — 필터·대량 행·사람 확인 반영
  http.get(mswPath('/snapshots/:sid/complexes'), async ({ request }) => {
    const page = await base<ComplexRowPage>(request);
    const url = new URL(request.url);
    const n = Number(readFlag(MOCK_ROWS_KEY) ?? '0');
    const all = n > 0 ? multiplyRows(page.items, n) : page.items;
    const items = filterRows(all, url).map(applyIntake);
    const size = Number(url.searchParams.get('size') ?? page.size);
    const pageNo = Number(url.searchParams.get('page') ?? '1');
    const start = (pageNo - 1) * size;
    return HttpResponse.json({
      ...page,
      items: items.slice(start, start + size),
      total: items.length,
      page: pageNo,
      size,
      sort: url.searchParams.get('sort') ?? page.sort,
    } satisfies ComplexRowPage);
  }),

  // GET /complexes/{id} — 요청 id의 이름·접수 상태로 헤더를 맞춘다(예시는 단지 1개)
  http.get(mswPath('/complexes/:id'), async ({ request, params }) => {
    const detail = await base<ComplexDetail>(request);
    const id = Number(params.id);
    const page = await base<ComplexRowPage>(
      new Request(new URL('/api/snapshots/0/complexes', request.url).toString()),
    );
    const row = page.items.find((r) => r.complex_id === id);
    const override = state.intakeOverrides.get(id);
    const header = row ? { ...detail.header, id, name: row.name } : detail.header;
    // 계약 .10 초안: 서버 차감 여부. 예시에 없으면 '빼지 않음'(예시 단지는 할인 없음)
    const draft: PriceRangeWithApplied = detail.price;
    const price: PriceRangeWithApplied = {
      ...draft,
      discount_applied: draft.discount_applied ?? false,
    };
    return HttpResponse.json({
      ...detail,
      header,
      price,
      intake_current: override ?? (row ? row.intake : detail.intake_current),
      intake: override ? [override, ...detail.intake] : detail.intake,
    } satisfies ComplexDetail);
  }),

  // GET /snapshots/{sid}/market — 계약 .10 초안: ?scenario=(Scenario 파라미터) 검증. 응답 모양은 예시 그대로
  http.get(mswPath('/snapshots/:sid/market'), async ({ request }) => {
    const scenario = new URL(request.url).searchParams.get('scenario');
    if (scenario !== null && !/^(base|A|B|C|D|[0-9]+)$/.test(scenario)) {
      return HttpResponse.json(
        { code: 'validation_error', detail: `scenario: ${scenario}` },
        { status: 422 },
      );
    }
    return HttpResponse.json(await base<Market>(request));
  }),

  // POST /jobs (202) — 상태 있는 잡
  http.post(mswPath('/jobs'), async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as Partial<JobCreate>;
    const job = registerJob(body.job_name ?? 'rejudge', body.payload ?? {});
    return HttpResponse.json(job, { status: 202 });
  }),

  // POST /reports (202 → JobRun) — 상태 있는 잡
  http.post(mswPath('/reports'), async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as Partial<ReportRequest>;
    const job = registerJob('report', { ...body });
    return HttpResponse.json(job, { status: 202 });
  }),

  // POST /regions (201) — 예시 응답 + 그 job_id를 상태 있는 잡으로
  http.post(mswPath('/regions'), async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
    const created = await base<RegionCreated>(request, 'POST', body);
    registerJob('region.bootstrap', { region_id: created.region.id }, created.job_id);
    return HttpResponse.json(
      {
        ...created,
        region: {
          ...created.region,
          name: typeof body.name === 'string' ? body.name : created.region.name,
        },
      },
      { status: 201 },
    );
  }),

  // PATCH /regions/{id} — 생성 핸들러 응답(계약 예시 RegionPatched) 그대로 + 그 job_id 를 상태 있는 region.expand 잡으로
  http.patch(mswPath('/regions/:id'), async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
    const patched = await base<RegionPatched>(request, 'PATCH', body);
    if (patched.job_id !== null) {
      registerJob('region.expand', { region_id: patched.region.id }, patched.job_id);
    }
    return HttpResponse.json(patched);
  }),

  // PATCH /claims/{id} (202 → claim.reverify 잡) — 상태 있는 잡
  http.patch(mswPath('/claims/:id'), async ({ request, params }) => {
    const body = (await request.json().catch(() => ({}))) as Partial<ClaimPatch>;
    const example = await base<JobRun>(request, 'PATCH', body);
    const job = registerJob('claim.reverify', {
      ...example.payload,
      claim_id: Number(params.id),
      text: body.text ?? '',
    });
    return HttpResponse.json(job, { status: 202 });
  }),

  // POST /catalysts (201) — 예시 응답 + 요청 값, 분류 잡은 상태 있는 잡
  http.post(mswPath('/catalysts'), async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as Partial<CatalystCreate>;
    const created = await base<CatalystCreated>(request, 'POST', body);
    const job = created.job ? registerJob(created.job.job_name, created.job.payload) : null;
    return HttpResponse.json(
      {
        catalyst: {
          ...created.catalyst,
          name: body.title ?? created.catalyst.name,
          source_url: body.url ?? created.catalyst.source_url,
        },
        job,
      } satisfies CatalystCreated,
      { status: 201 },
    );
  }),

  // POST /share-links (201) — 요청 label 반영
  http.post(mswPath('/share-links'), async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as Partial<ShareLinkCreate>;
    const created = await base<ShareLinkCreated>(request, 'POST', body);
    return HttpResponse.json(
      {
        ...created,
        link: { ...created.link, label: body.label ?? null },
      } satisfies ShareLinkCreated,
      { status: 201 },
    );
  }),

  // GET /jobs/{id} — 등록된 잡이면 폴링마다 진행, 아니면 예시
  http.get(mswPath('/jobs/:id'), async ({ request, params }) => {
    const entry = state.jobs.get(Number(params.id));
    if (entry) return HttpResponse.json(advanceJob(entry));
    return HttpResponse.json(await base<JobRun>(request));
  }),

  // POST /ops/human-checks (201) — 응답을 요청 값으로 맞추고 intake를 덮어쓴다
  http.post(mswPath('/ops/human-checks'), async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as HumanCheckCreate;
    const example = await base<HumanCheck>(request, 'POST', body);
    // 계약 .9(D12-5): 서버가 rejudge 를 자동 등록 → rejudge_job_id(상태 있는 잡). '기타'는 잡 없음
    const rejudgePayload = {
      ...(example.suggested_job?.payload ?? {}),
      complex_ids: [body.complex_id],
    };
    const auto = body.field === 'other' ? null : registerJob('rejudge', rejudgePayload);
    const jobFields = {
      rejudge_job_id: auto?.id ?? null,
      suggested_job: auto ? { job_name: 'rejudge' as const, payload: rejudgePayload } : null,
    };
    if (body.field !== 'intake_status') {
      // 사실 필드: 접수 행 없음(접수 배지는 그대로). 사실 행(entity·entity_id)은 서버가 정한다 — 목은 비운다
      return HttpResponse.json(
        {
          ...example,
          ...body,
          entity: null,
          entity_id: null,
          note: body.note ?? null,
          created_intake: null,
          ...jobFields,
        } satisfies HumanCheck,
        { status: 201 },
      );
    }
    const intake: Intake = {
      ...(example.created_intake ?? {
        status: '가능',
        path: 'human_check',
        checked_at: body.checked_at,
      }),
      complex_id: body.complex_id,
      path: 'human_check',
      status:
        body.field === 'intake_status' &&
        ['가능', '미정', '확인 불가', '불가'].includes(body.value_text)
          ? (body.value_text as Intake['status'])
          : (example.created_intake?.status ?? '가능'),
      checked_at: body.checked_at,
      note: body.note ?? null,
      entered_by: body.entered_by,
    };
    if (body.field === 'intake_status') state.intakeOverrides.set(body.complex_id, intake);
    const created: HumanCheck = {
      ...example,
      ...body,
      note: body.note ?? null,
      id: example.id,
      created_intake: intake,
      ...jobFields,
    };
    return HttpResponse.json(created, { status: 201 });
  }),

  // GET /raw/{id}?as=text — 원문 텍스트(목). 출처 예시의 발췌를 excerpt_start 위치에 둔다
  http.get(mswPath('/raw/:id'), async ({ request, params }) => {
    const url = new URL(request.url);
    if (url.searchParams.get('as') !== 'text') {
      return new HttpResponse(`raw document ${String(params.id)}`, {
        headers: { 'Content-Type': 'text/plain; charset=utf-8' },
      });
    }
    const prov = await base<Provenance>(
      new Request(new URL('/api/provenance/mock', request.url).toString()),
    );
    const excerpt = prov.excerpt ?? '';
    const start = prov.excerpt_start ?? 0;
    const head = '[원문 텍스트 · 목 데이터]\n';
    const filler = '…'.repeat(Math.max(0, start - head.length));
    const text = `${head}${filler}${excerpt}\n…(이하 생략)`;
    return new HttpResponse(text, { headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
  }),

  // GET /reports/{id} — 다운로드 파일(목)
  http.get(mswPath('/reports/:id'), ({ params }) => {
    return new HttpResponse(`<!doctype html><title>report ${String(params.id)}</title>`, {
      headers: { 'Content-Type': 'text/html; charset=utf-8' },
    });
  }),
];
