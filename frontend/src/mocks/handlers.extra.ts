/**
 * 수동 보강 핸들러 (WP6a 소유) — 생성물(handlers.gen.ts)에 없거나 예시 하나만으로 부족한 동작.
 * 여기 핸들러가 생성 핸들러보다 **먼저** 매칭된다(handlers.ts 순서).
 *
 * 원칙: 응답 모양은 생성 핸들러(=계약 예시)에서 `getResponse`로 받아 그대로 쓰고, 상태만 덧붙인다.
 *  - 잡: POST /jobs·/reports·/regions 가 만든 잡은 GET /jobs/{id} 폴링마다 queued → running → done
 *  - 사람 확인: POST /ops/human-checks 후 단지 목록·상세의 intake가 그 값으로 바뀐다(배지 즉시 갱신)
 *  - G2 대량 행: localStorage `msw.complexes.rows` = N 이면 예시 행을 N개로 복제(가상 스크롤 확인용)
 *  - 판정기 장애: localStorage `msw.degraded` = 1 이면 /health status=degraded
 *  - 원문 텍스트: GET /raw/{id}?as=text (생성기가 건너뜀), GET /reports/{id}
 *  - 주장 수정 PATCH /claims/{id}·호재 URL POST /catalysts 가 만든 잡도 상태 있는 잡(계약 2026-10-09.4)
 *  - 공유 링크 POST /share-links: 요청 label 을 응답에 반영
 *  - 호재 위치 PATCH /catalysts/{id}(계약 .8 초안): 위치 확인 → 링크, GET market 에 반영
 *  - 지역 확장 PATCH /regions/{id}(계약 .8 초안): selections 교체 + region.expand 잡
 *  - 계약 .8 초안(src/api/contract8.ts): 사람 확인 field enum·값 형·길이 검사(422), 사실 필드 사람 확인 → 같은 단지·필드의
 *    강등(GET claims demotion)을 복원(restored_by human_check). CORE 머지 후 생성 핸들러로 바뀌는 부분은 여기서만 흉내 낸다.
 * 지역명은 목 데이터(계약 예시)에만 있다.
 */
import { getResponse, http, HttpResponse, type RequestHandler } from 'msw';
import type {
  CatalystCreate,
  CatalystCreated,
  ClaimPatch,
  ClaimView,
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
  Provenance,
  Region,
  RegionCreated,
  Snapshot,
  ReportRequest,
  ShareLinkCreate,
  ShareLinkCreated,
} from '@/api/types';
import {
  type CatalystLink,
  type CatalystPatch,
  type RegionPatch,
  HUMAN_CHECK_FIELDS,
  HUMAN_CHECK_NOTE_MAX,
  HUMAN_CHECK_RULES,
  HUMAN_CHECK_VALUE_MAX,
  humanCheckFieldOf,
  type HumanCheckField,
} from '@/api/contract8';
import { generatedHandlers } from './handlers.gen';
import { mswPath } from './mswPath';

export const MOCK_ROWS_KEY = 'msw.complexes.rows';
export const MOCK_DEGRADED_KEY = 'msw.degraded';
/** localStorage `msw.revisions` = 1 이면 최신 기준일에 발행 리비전 2(계약 .8 초안 D11-1)를 덧붙인다 */
export const MOCK_REVISIONS_KEY = 'msw.revisions';
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
  /** 사람 확인으로 복원된 사실: `<complex_id>:<field>` (계약 .8 초안) */
  restoredFacts: new Set<string>(),
  /** 사람이 확인한 호재 위치(계약 .8 초안 PATCH /catalysts/{id}) */
  catalystLocations: new Map<number, { confirmed: boolean; complexIds: number[] }>(),
};

/** 테스트 사이 초기화(src/test/setup.ts가 resetHandlers 때 부를 수 있다) */
export function resetMockState(): void {
  state.nextJobId = 5000;
  state.jobs.clear();
  state.intakeOverrides.clear();
  state.restoredFacts.clear();
  state.catalystLocations.clear();
}

/** 계약 .8 초안 사람 확인 검사 — 서버(422)와 같은 규칙. 통과하면 null */
function humanCheckProblem(body: Partial<HumanCheckCreate>): string | null {
  const field = body.field as HumanCheckField;
  if (!(HUMAN_CHECK_FIELDS as readonly string[]).includes(field))
    return `field: ${String(body.field)}`;
  const value = (body.value_text ?? '').trim();
  if (!value || value.length > HUMAN_CHECK_VALUE_MAX) return 'value_text 길이';
  if ((body.note ?? '').length > HUMAN_CHECK_NOTE_MAX) return 'note 길이';
  const rule = HUMAN_CHECK_RULES[field];
  if (!rule) return null;
  if (rule.kind === 'ym') return /^\d{4}-(0[1-9]|1[0-2])$/.test(value) ? null : 'YYYY-MM';
  if (!(rule.kind === 'int' ? /^-?\d+$/ : /^-?\d+(\.\d+)?$/).test(value)) return '숫자 형식';
  const n = Number(value);
  if ((rule.min !== undefined && n < rule.min) || (rule.max !== undefined && n > rule.max))
    return '범위';
  return null;
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

  // GET /regions/{id}/snapshots — 리비전(계약 .8 초안): 없는 필드는 1, 플래그면 최신 기준일 리비전 2
  http.get(mswPath('/regions/:id/snapshots'), async ({ request }) => {
    const list = (await base<Snapshot[]>(request)).map((s) => ({
      revision: 1,
      revision_of: null,
      revision_reason: null,
      ...s,
    }));
    if (readFlag(MOCK_REVISIONS_KEY) !== '1' || list.length === 0) return HttpResponse.json(list);
    const latest = list[0]!;
    const rev2 = {
      ...latest,
      id: Math.max(...list.map((s) => s.id)) + 1,
      revision: 2,
      revision_of: latest.id,
      revision_reason: '사람 확인 입력(재판정)',
      status: 'published' as const,
    };
    return HttpResponse.json([rev2, ...list]);
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
    const body = (await request.json().catch(() => ({}))) as HumanCheckCreate & {
      entity_id?: number | null;
    };
    const problem = humanCheckProblem(body);
    if (problem)
      return HttpResponse.json({ detail: `사람 확인 값 오류: ${problem}` }, { status: 422 });
    const example = await base<HumanCheck>(request, 'POST', body);
    if (body.field !== 'intake_status') {
      // 사실 필드(계약 .8): 0순위 후보 → 같은 단지·필드 강등 복원. 접수 배지는 그대로
      state.restoredFacts.add(`${body.complex_id}:${body.field}`);
      const entity = ['max_price_won', 'down_payment_pct'].includes(body.field)
        ? 'payment_terms'
        : body.field === 'other'
          ? null
          : 'complex';
      return HttpResponse.json(
        {
          ...example,
          ...body,
          entity,
          entity_id: entity ? (body.entity_id ?? body.complex_id) : null,
          note: body.note ?? null,
          created_intake: null,
          suggested_job: {
            job_name: 'rejudge',
            payload: { ...(example.suggested_job?.payload ?? {}), complex_ids: [body.complex_id] },
          },
        },
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
      suggested_job: {
        job_name: 'rejudge',
        payload: {
          ...(example.suggested_job?.payload ?? {}),
          complex_ids: [body.complex_id],
        },
      },
    };
    return HttpResponse.json(created, { status: 201 });
  }),

  // PATCH /regions/{id} (계약 .8 초안, D11-7) — 지역 선택 확장 → Region + region.expand 잡(새 리비전 rerank)
  http.patch(mswPath('/regions/:id'), async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as Partial<RegionPatch>;
    const selections = body.selections ?? [];
    if (selections.length === 0) {
      return HttpResponse.json({ detail: '선택이 하나 이상 필요합니다' }, { status: 422 });
    }
    const region = await base<Region>(new Request(request.url));
    const job = registerJob('region.expand' as JobName, { region_id: region.id });
    return HttpResponse.json({ region: { ...region, selections }, job });
  }),

  // PATCH /catalysts/{id} (계약 .8 초안, D11-5) — 위치 확인 → catalyst_link(목: 단지 좌표 없음 → 거리 null·가중치 1·추정)
  http.patch(mswPath('/catalysts/:id'), async ({ request, params }) => {
    const body = (await request.json().catch(() => ({}))) as Partial<CatalystPatch>;
    const id = Number(params.id);
    const market = await base<Market>(
      new Request(new URL('/api/snapshots/0/market', request.url).toString()),
    );
    const catalyst = market.catalysts.find((c) => c.id === id);
    if (!catalyst) return HttpResponse.json({ detail: 'catalyst 없음' }, { status: 404 });
    const confirmed = body.location_confirmed === true;
    const hasCoord = typeof body.lat === 'number' && typeof body.lon === 'number';
    const areas = body.living_area_ids ?? [];
    const picked = body.complex_ids ?? [];
    if (confirmed && !hasCoord && areas.length === 0 && picked.length === 0) {
      return HttpResponse.json(
        { detail: '좌표 또는 영향 생활권·단지가 필요합니다' },
        { status: 422 },
      );
    }
    let ids: number[] = [];
    if (confirmed) {
      const page = await base<ComplexRowPage>(
        new Request(new URL('/api/snapshots/0/complexes', request.url).toString()),
      );
      const inAreas = page.items
        .filter((r) => r.living_area !== null && areas.includes(r.living_area ?? ''))
        .map((r) => r.complex_id);
      ids = [...new Set([...picked, ...inAreas])];
    }
    state.catalystLocations.set(id, { confirmed, complexIds: ids });
    const links: CatalystLink[] = ids.map((cid) => ({
      complex_id: cid,
      distance_m: null,
      weight: 1,
      label: '추정',
    }));
    return HttpResponse.json({
      catalyst: {
        ...catalyst,
        location_confirmed: confirmed,
        linked: ids.length > 0,
        linked_complex_ids: ids,
      },
      links,
    });
  }),

  // GET /snapshots/{sid}/market — 사람이 확인한 호재 위치 반영(계약 .8 초안)
  http.get(mswPath('/snapshots/:sid/market'), async ({ request }) => {
    const market = await base<Market>(request);
    if (state.catalystLocations.size === 0) return HttpResponse.json(market);
    return HttpResponse.json({
      ...market,
      catalysts: market.catalysts.map((c) => {
        const loc = state.catalystLocations.get(c.id);
        return loc
          ? {
              ...c,
              location_confirmed: loc.confirmed,
              linked: loc.complexIds.length > 0,
              linked_complex_ids: loc.complexIds,
            }
          : c;
      }),
    } satisfies Market);
  }),

  // GET /snapshots/{sid}/claims — 사람 확인으로 복원된 사실의 강등 상태(계약 .8 초안)
  http.get(mswPath('/snapshots/:sid/claims'), async ({ request }) => {
    const claims = await base<ClaimView[]>(request);
    return HttpResponse.json(
      claims.map((claim) => {
        const d = claim.demotion;
        const field = humanCheckFieldOf(d?.field) ?? humanCheckFieldOf(claim.field);
        if (!d || d.status !== 'demoted' || !field) return claim;
        if (!state.restoredFacts.has(`${claim.complex_id}:${field}`)) return claim;
        return {
          ...claim,
          demotion: { ...d, status: 'restored', restored_by: 'human_check', restored_at: nowIso() },
        } satisfies ClaimView;
      }),
    );
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
