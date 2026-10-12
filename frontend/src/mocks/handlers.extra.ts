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
 *  - 계약 .11(D14-5·D14-6): PATCH /catalysts 202 + job_id(snapshot.publish, 상태 있는 잡), PATCH /regions 선택 변경 202 ·
 *    이름만 200, 사람 확인 201 + job_id. 사람 확인 checked_at 은 시간대 있는 RFC3339 · 10분 넘는 미래 422(서버와 같은 검사)
 *  - 계약 .13(D16-4): PATCH /catalysts 는 같은 호재에 같은 본문을 다시 보내면 200 + job_id null(바뀐 것 없음), 처음·다른
 *    본문이면 202 + job_id(예시 `catalyst_updated.json` 의 snapshot.publish 를 상태 있는 잡으로). 생성 핸들러는 가장 낮은
 *    상태(200 `catalyst_unchanged.json`)를 고르므로 202 모양은 계약 예시 파일에서 읽는다.
 *  - 계약 .14 F3·F4·F11(R3i m2·m10): 사람 확인 숫자 값은 서버(`demotion.py` parse_human_value)와 같은 엄격한 규칙
 *    (`humanCheckRules.parseStrictNumber`)으로 검사한다. 할인만 틀리면 422 `discount_format`, 할인 ≥ 기준 타입 차감 바탕
 *    (예시 상세 기준 타입 min(대표층가, 최고가))이면 `discount_not_below_price`, 다른 칸도 틀리면 `validation_error` + 모든
 *    칸(checked_at 먼저). 할인 201 응답 `basis_type_code` = 예시 상세 기준 타입(F2)
 *  - 계약 .14 F5: PATCH /ops/checklist 상태·메모·기한이 바뀌면 202 + job_id(snapshot.publish 상태 있는 잡), 같으면 200 + null
 *  - 계약 .14 F6: PATCH /regions 선택 그대로 + 이름만 → 202 + snapshot.publish 잡(change_event null)
 *  - 계약 .14 F7: PATCH /catalysts 좌표는 소수 6자리 반올림으로 비교(같으면 200)
 *  - 계약 .15 F3: POST /regions 선택 필드 applyhome_query — 서버와 같은 'YYYY-MM' 패턴 검사(틀리면 422 validation_error +
 *    field_errors loc ['body','applyhome_query',<키>]), 맞으면 응답 region.applyhome_query 에 그대로
 *  - 계약 .8(리비전·사람 확인 field·PATCH /catalysts·PATCH /regions)은 생성 핸들러(계약 예시)를 그대로 쓴다 — 초안 목 없음.
 *    상태가 필요한 테스트는 server.use 로 개별 덮어쓴다.
 * 지역명은 목 데이터(계약 예시)에만 있다.
 */
import { getResponse, http, HttpResponse, type RequestHandler } from 'msw';
import type {
  CatalystCreate,
  CatalystCreated,
  CatalystPatch,
  CatalystUpdated,
  ChecklistItem,
  ClaimPatch,
  ComplexDetail,
  ComplexRow,
  ComplexRowPage,
  Health,
  HumanCheck,
  HumanCheckCreate,
  HumanCheckField,
  Intake,
  JobCreate,
  JobName,
  JobRun,
  Provenance,
  Region,
  RegionCreated,
  RegionPatched,
  ReportRequest,
  ShareLinkCreate,
  ShareLinkCreated,
} from '@/api/types';
import catalystUpdatedExample from '../../../contracts/examples/catalyst_updated.json';
import { HUMAN_CHECK_RULES, parseStrictNumber } from '@/pages/ops/humanCheckRules';
import { YM_PATTERN } from '@/pages/region-new/applyhomeWindow';
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

/**
 * 계약 .15 F3: POST /regions `applyhome_query`(region.json ApplyhomeQuery) 검사 — 객체, from_ym·to_ym 은 string|null 이고
 * 'YYYY-MM'(월 01~12) 패턴, areas 는 문자열 값 객체. 서버(jsonschema)와 같은 loc ['body','applyhome_query',<키>].
 */
function applyhomeQueryErrors(aq: unknown): { loc: string[]; msg: string }[] {
  const loc = (key?: string) => ['body', 'applyhome_query', ...(key ? [key] : [])];
  if (aq === null || typeof aq !== 'object' || Array.isArray(aq)) {
    return [{ loc: loc(), msg: 'is not of type object' }];
  }
  const errors: { loc: string[]; msg: string }[] = [];
  const q = aq as Record<string, unknown>;
  for (const key of ['from_ym', 'to_ym'] as const) {
    const v = q[key];
    if (v === undefined || v === null) continue;
    if (typeof v !== 'string') errors.push({ loc: loc(key), msg: 'is not of type string' });
    else if (!YM_PATTERN.test(v))
      errors.push({ loc: loc(key), msg: `'${v}' does not match pattern` });
  }
  const areas = q.areas;
  if (
    areas !== undefined &&
    (areas === null ||
      typeof areas !== 'object' ||
      Array.isArray(areas) ||
      Object.values(areas).some((x) => typeof x !== 'string'))
  ) {
    errors.push({ loc: loc('areas'), msg: 'is not an object of strings' });
  }
  return errors;
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
  /** PATCH /catalysts 마지막 본문(호재 id → JSON) — 같은 본문이면 바뀐 것 없음(200) */
  catalystPatches: new Map<number, string>(),
  /** PATCH /ops/checklist 로 바뀐 항목(항목 id → 상태·메모·기한) — 없으면 예시 목록 값(계약 .14 F5) */
  checklist: new Map<number, ChecklistState>(),
};

/** 계약 예시 PATCH /catalysts 202(보이는 값이 바뀜 — 계약 .13 D16-4) */
const CATALYST_UPDATED = (catalystUpdatedExample as { value: CatalystUpdated }).value;

/** 테스트 사이 초기화(src/test/setup.ts가 resetHandlers 때 부를 수 있다) */
export function resetMockState(): void {
  state.nextJobId = 5000;
  state.jobs.clear();
  state.intakeOverrides.clear();
  state.catalystPatches.clear();
  state.checklist.clear();
}

type ChecklistState = Pick<ChecklistItem, 'status' | 'note' | 'due_date'>;
type FieldError = { loc: (string | number)[]; msg: string };

/**
 * 서버 parse_human_value(계약 .14 F3·F4)와 같은 값 검사 — 숫자 필드만(연월·접수·기타는 생성 예시 그대로). 문제가 없으면
 * null, 있으면 문구.
 */
function humanValueProblem(field: HumanCheckField, value: unknown): string | null {
  const rule = HUMAN_CHECK_RULES[field];
  if (!rule || rule.kind === 'ym') return null;
  const text = typeof value === 'string' ? value : '';
  const parsed = parseStrictNumber(field, text);
  if (!parsed.ok) {
    return parsed.reason === 'format'
      ? `'${text}' 은 ${field} 값(ASCII 숫자 — 쉼표는 세 자리마다)이 아니다`
      : `'${text}' 은 ${field} 범위 밖이다`;
  }
  if (rule.kind === 'int' && parsed.decimals > 0) return `'${text}' 은 정수가 아니다(${field})`;
  if (
    (rule.min !== undefined && parsed.value < rule.min) ||
    (rule.max !== undefined && parsed.value > rule.max)
  ) {
    return `'${text}' 은 ${field} 범위(${rule.min ?? ''}~${rule.max ?? ''}) 밖이다`;
  }
  if (rule.decimals !== undefined && parsed.decimals > rule.decimals) {
    return `'${text}' 은 소수 둘째 자리까지만 받는다`;
  }
  return null;
}

/** 예시 상세의 기준 타입·할인 상한(배타) = min(대표층가, 최고가)(서버 discount_ceiling) */
async function discountBasis(
  request: Request,
  complexId: number,
): Promise<{ basis: string | null; ceiling: number | null }> {
  const detailUrl = new URL(request.url);
  detailUrl.pathname = detailUrl.pathname.replace(
    /\/ops\/human-checks$/,
    `/complexes/${complexId}`,
  );
  const detail = await base<ComplexDetail>(new Request(detailUrl));
  const basis = detail.price.basis_type_code ?? null;
  const row = detail.types.find((r) => r.type_code === basis) ?? null;
  const top = typeof row?.max_price_won.v === 'number' ? row.max_price_won.v : null;
  const floor =
    typeof row?.floor_sample_price_won.v === 'number' ? row.floor_sample_price_won.v : null;
  return { basis, ceiling: top === null ? null : floor === null ? top : Math.min(top, floor) };
}

const nowIso = () => new Date().toISOString();

/**
 * 서버(app/api/demotion.py) checked_at 검사와 같은 규칙(계약 .12 F8·F14) — 문제가 없으면 null, 있으면 [code, 문구].
 * 형식·KST 2000-01-01 이전 = checked_at_format, 지금 + 10분 넘는 미래 = checked_at_future.
 */
function checkedAtProblem(
  value: unknown,
): ['checked_at_format' | 'checked_at_future', string] | null {
  const rfc3339 = /^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(\.\d{1,9})?([Zz]|[+-]\d{2}:\d{2})$/;
  if (typeof value !== 'string' || !rfc3339.test(value)) {
    return ['checked_at_format', 'checked_at 은 시간대가 붙은 RFC3339 date-time 이어야 한다'];
  }
  const at = Date.parse(value.toUpperCase());
  if (!Number.isFinite(at) || at < Date.parse('2000-01-01T00:00:00+09:00')) {
    return ['checked_at_format', 'checked_at 은 2000-01-01(KST) 이후여야 한다'];
  }
  if (at - Date.now() > 10 * 60_000) {
    return ['checked_at_future', `checked_at ${value} 은 지금보다 10분 넘게 미래다`];
  }
  return null;
}

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

/**
 * 계약 .12 F15: 끝난 잡의 stats `publish_job_id` — rejudge 는 판정 뒤 등록한 snapshot.publish 잡(목도 등록한다),
 * snapshot.publish·region.expand·region.bootstrap 은 그 자리 발행(자기 자신 + published true). 그 밖(보고서·재검증)은 없음.
 */
function doneStats(job: JobRun): Record<string, unknown> {
  const sid = typeof job.payload.snapshot_id === 'number' ? job.payload.snapshot_id : null;
  switch (job.job_name) {
    case 'rejudge': {
      const publish = registerJob('snapshot.publish', { snapshot_id: sid });
      return { ...job.stats, snapshot_id: sid, publish_job_id: publish.id };
    }
    case 'snapshot.publish':
    case 'region.expand':
    case 'region.bootstrap':
      return { ...job.stats, snapshot_id: sid, publish_job_id: job.id, published: true };
    default:
      return job.stats;
  }
}

function advanceJob(entry: MockJob): JobRun {
  entry.polls += 1;
  const { job } = entry;
  if (job.status === 'done' || job.status === 'failed') return job;
  if (entry.polls >= MOCK_JOB_POLLS_TO_DONE) {
    entry.job = {
      ...job,
      status: 'done',
      started_at: job.started_at ?? nowIso(),
      finished_at: nowIso(),
      progress: { done: 1, total: 1, step: null },
      stats: doneStats(job),
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
    return HttpResponse.json({
      ...detail,
      header,
      intake_current: override ?? (row ? row.intake : detail.intake_current),
      intake: override ? [override, ...detail.intake] : detail.intake,
    } satisfies ComplexDetail);
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

  // POST /regions (201) — 예시 응답 + 그 job_id를 상태 있는 잡으로.
  // 계약 .15 F3: 선택 필드 applyhome_query 는 서버와 같은 패턴 검사(틀리면 422 validation_error), 맞으면 region.applyhome_query 그대로
  http.post(mswPath('/regions'), async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
    const aq = body.applyhome_query;
    if (aq !== undefined) {
      const fieldErrors = applyhomeQueryErrors(aq);
      if (fieldErrors.length > 0) {
        return HttpResponse.json(
          {
            code: 'validation_error',
            detail: fieldErrors.map((e) => `${e.loc.slice(1).join('.')}: ${e.msg}`).join('; '),
            field_errors: fieldErrors,
          },
          { status: 422 },
        );
      }
    }
    const created = await base<RegionCreated>(request, 'POST', body);
    registerJob('region.bootstrap', { region_id: created.region.id }, created.job_id);
    return HttpResponse.json(
      {
        ...created,
        region: {
          ...created.region,
          name: typeof body.name === 'string' ? body.name : created.region.name,
          applyhome_query:
            aq !== undefined ? (aq as Record<string, unknown>) : created.region.applyhome_query,
        },
      },
      { status: 201 },
    );
  }),

  // PATCH /regions/{id} — 생성 핸들러 응답(계약 예시 RegionPatched) 그대로 + 그 job_id 를 상태 있는 region.expand 잡으로
  http.patch(mswPath('/regions/:id'), async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
    // 계약 .14 F6(D17-5): 선택이 그대로면(이름만) 발행 리비전 보고서 표지만 바뀐다 → 202 + snapshot.publish 잡
    const current = await base<Region>(request);
    const keyOf = (list: unknown) =>
      Array.isArray(list)
        ? (list as { kind?: unknown; code?: unknown }[])
            .map((x) => `${String(x.kind)}:${String(x.code)}`)
            .sort()
            .join('|')
        : null;
    if (keyOf(body.selections) === keyOf(current.selections) && typeof body.name === 'string') {
      const job = registerJob('snapshot.publish', {
        snapshot_id: current.latest_snapshot?.id ?? null,
      });
      return HttpResponse.json(
        {
          region: { ...current, name: body.name },
          change_event: null,
          job_id: job.id,
          added: [],
          removed: [],
        } satisfies RegionPatched,
        { status: 202 },
      );
    }
    const patched = await base<RegionPatched>(request, 'PATCH', body);
    if (patched.job_id !== null) {
      registerJob('region.expand', { region_id: patched.region.id }, patched.job_id);
    }
    // 계약 .11 F5: 선택이 바뀌면 202, 이름만이면 200
    return HttpResponse.json(patched, { status: patched.job_id !== null ? 202 : 200 });
  }),

  // PATCH /catalysts/{id} — 계약 .13 F3(D16-4): 보이는 값이 바뀌면 202 + job_id(snapshot.publish, 상태 있는 잡),
  // 같은 본문을 다시 보내면 바뀐 것 없음 200 + job·job_id null(생성 핸들러 = catalyst_unchanged 예시)
  http.patch(mswPath('/catalysts/:id'), async ({ request, params }) => {
    const body = (await request.json().catch(() => ({}))) as Partial<CatalystPatch>;
    const id = Number(params.id);
    // 계약 .14 F7(m8): 좌표는 저장 자리(소수 6자리, 반올림)로 비교
    const round6 = (v: number | null | undefined) =>
      typeof v === 'number' ? Math.round(v * 1e6) / 1e6 : v;
    const key = JSON.stringify({ ...body, lat: round6(body.lat), lon: round6(body.lon) });
    if (state.catalystPatches.get(id) === key) {
      const unchanged = await base<CatalystUpdated>(request, 'PATCH', body);
      return HttpResponse.json(
        { ...unchanged, job: null, job_id: null } satisfies CatalystUpdated,
        { status: 200 },
      );
    }
    state.catalystPatches.set(id, key);
    const job = CATALYST_UPDATED.job
      ? registerJob('snapshot.publish', CATALYST_UPDATED.job.payload)
      : null;
    return HttpResponse.json(
      { ...CATALYST_UPDATED, job, job_id: job?.id ?? null } satisfies CatalystUpdated,
      { status: 202 },
    );
  }),

  // PATCH /ops/checklist/{id} — 계약 .14 F5(D17-5): 상태·메모·기한이 실제로 바뀌면 202 + job_id(snapshot.publish, 상태 있는
  // 잡), 같으면 200 + job_id null. 응답 모양은 생성 핸들러(계약 예시)에 요청 값을 얹는다
  http.patch(mswPath('/ops/checklist/:id'), async ({ request, params }) => {
    const body = (await request.json().catch(() => ({}))) as Partial<ChecklistState>;
    const id = Number(params.id);
    const example = await base<ChecklistItem>(request, 'PATCH', body);
    let before = state.checklist.get(id);
    if (!before) {
      const list = await base<ChecklistItem[]>(
        new Request(new URL(request.url.replace(/\/\d+$/, '')).toString()),
      );
      const row = list.find((x) => x.id === id);
      before = row
        ? { status: row.status, note: row.note, due_date: row.due_date }
        : { status: example.status, note: example.note, due_date: example.due_date };
    }
    const after: ChecklistState = {
      status: body.status ?? before.status,
      note: body.note === undefined ? before.note : body.note,
      due_date: body.due_date === undefined ? before.due_date : body.due_date,
    };
    state.checklist.set(id, after);
    const changed =
      after.status !== before.status ||
      after.note !== before.note ||
      after.due_date !== before.due_date;
    const job = changed ? registerJob('snapshot.publish', { snapshot_id: 12 }) : null;
    return HttpResponse.json(
      { ...example, id, ...after, job_id: job?.id ?? null } satisfies ChecklistItem,
      { status: changed ? 202 : 200 },
    );
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
        job_id: job?.id ?? null,
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
    // 계약 .11 F7(D14-6): 시간대가 붙은 RFC3339 만, 서버 지금보다 10분 넘게 미래면 422
    const checkedAtError = checkedAtProblem(body.checked_at);
    // 계약 .14 F3·F4·F11: 값 칸 검사(엄격한 숫자) — checked_at 오류가 있어도 함께, checked_at 먼저
    const valueError = humanValueProblem(body.field, body.value_text);
    const errors: FieldError[] = [
      ...(checkedAtError ? [{ loc: ['body', 'checked_at'], msg: checkedAtError[1] }] : []),
      ...(valueError ? [{ loc: ['body', 'value_text'], msg: valueError }] : []),
    ];
    if (errors.length > 1) {
      return HttpResponse.json(
        { code: 'validation_error', detail: errors[0]!.msg, field_errors: errors },
        { status: 422 },
      );
    }
    if (checkedAtError) {
      const [code, detail] = checkedAtError;
      return HttpResponse.json(
        { code, detail, field_errors: [{ loc: ['body', 'checked_at'], msg: detail }] },
        { status: 422 },
      );
    }
    if (valueError) {
      return HttpResponse.json(
        {
          code: body.field === 'discount' ? 'discount_format' : 'validation_error',
          detail: valueError,
          field_errors: [{ loc: ['body', 'value_text'], msg: valueError }],
        },
        { status: 422 },
      );
    }
    const discount =
      body.field === 'discount' ? await discountBasis(request, body.complex_id) : null;
    if (discount !== null && discount.ceiling !== null) {
      const won = parseStrictNumber('discount', body.value_text);
      if (won.ok && won.value > 0 && won.value >= discount.ceiling) {
        const detail = `할인 ${won.value}원 은 기준 타입 차감 바탕(${discount.ceiling}원) 이상이다 — 구매가에서 뺄 수 없다`;
        return HttpResponse.json(
          {
            code: 'discount_not_below_price',
            detail,
            field_errors: [{ loc: ['body', 'value_text'], msg: detail }],
          },
          { status: 422 },
        );
      }
    }
    const example = await base<HumanCheck>(request, 'POST', body);
    // 계약 .9(D12-5): 서버가 rejudge 를 자동 등록 → rejudge_job_id(상태 있는 잡). '기타'는 잡 없음
    const rejudgePayload = {
      ...(example.suggested_job?.payload ?? {}),
      complex_ids: [body.complex_id],
    };
    const auto = body.field === 'other' ? null : registerJob('rejudge', rejudgePayload);
    const jobFields = {
      rejudge_job_id: auto?.id ?? null,
      job_id: auto?.id ?? null,
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
          // 계약 .14 F2: 할인이 들어간 기준 타입(그 밖 필드는 null)
          basis_type_code: discount?.basis ?? null,
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
