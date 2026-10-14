/**
 * R4 FE9 — 계약 2026-10-09.15 FE 차이 표(`contracts/CHANGELOG.md` .15 F1–F8) 화면 맞춤.
 *  - F1(D18-1·D20-1): 판정 봉투 `model`·`provider` → G3·G7 판정 로그 '모델' 열, provider 'none' = '로컬'(비용 없음)
 *  - F2(D18-2): G7 `real_calls` = 판정기로 실제 보낸 tools/call 수 — 타일 안내(호출 = 실제 + 캐시)
 *  - F3·F4(D20-1): G0 '청약홈 조회 기간(고급)' 선택 입력(`applyhome_query.from_ym`·`to_ym`) — 비우면 보내지 않음(서버 기본
 *    창 지난 24개월 + 향후 12개월), 형식은 서버와 같은 'YYYY-MM'(월 01~12), 서버 422 → 조회 기간 칸 안내. MSW 목도 같은 검사
 *  - F5(D20-2): 트랙 (A) 공고 예정 후보 — G3 머리 '공고 예정 후보(청약홈 미등록)'·범위 '보류 — 공고 후 재판정', G2 행(범위
 *    배지·'확인 불가(공고 전)'), G1·G2 변경 표기('공고 예정 후보'·'주택관리번호' 필드 이름)
 *  - F7(D18-7·m3): G1 '최근 변경'의 `region·first_load` 한 줄 = '지역 · 첫 적재' + 요약 문장(빈 값 → 화살표 없이)
 */
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { getResponse, http, HttpResponse, type RequestHandler } from 'msw';
import type {
  ChangeEvent,
  ComplexDetail,
  ComplexRowPage,
  Dashboard,
  JudgmentEnvelope,
  JudgmentOps,
  RegionCreated,
} from '@/api/types';
import { t } from '@/i18n';
import { generatedHandlers } from '@/mocks/handlers.gen';
import { handlers } from '@/mocks/handlers';
import { resetMockState } from '@/mocks/handlers.extra';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { renderRoute, renderWithProviders } from '@/test/render';
import { JudgmentTable } from './complex/JudgmentsTab';
import { matching, recordRequests } from './_shared/testing';

vi.mock('@/charts/EChartRuntime', () => ({ default: () => null }));
beforeEach(() => resetMockState());

async function example<T>(path: string): Promise<T> {
  const res = await getResponse(
    generatedHandlers as RequestHandler[],
    new Request(`http://localhost/api${path}`),
  );
  return (await res?.json()) as T;
}

/** 목 전체(보강 → 생성 순서)로 요청 — MSW 목 동작 확인용 */
async function mock(path: string, init: RequestInit): Promise<Response> {
  const res = await getResponse(
    handlers as RequestHandler[],
    new Request(`http://localhost/api${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json' },
    }),
  );
  if (!res) throw new Error(`no mock for ${path}`);
  return res;
}

/** '확인 불가(공고 전' 으로 시작(확인일이 붙으면 '확인 불가(공고 전, 2026-10-07)') */
const preNotice = new RegExp(
  `^${t('empty.unknownWithReason', { reason: t('empty.reasonPlain.pre_notice') })
    .slice(0, -1)
    .replace(/[()]/g, '\\$&')}`,
);

function envelope(
  base: JudgmentEnvelope,
  seq: number,
  model: string | null,
  provider: string | null,
): JudgmentEnvelope {
  return { ...base, judgment_seq: seq, input_hash: `sha256:${seq}`, model, provider };
}

describe('F1(D18-1·D20-1) 판정 봉투 model·provider → 판정 로그 모델 열', () => {
  async function rows(): Promise<JudgmentEnvelope[]> {
    const ops = await example<JudgmentOps>('/ops/judgments');
    const base = ops.items[0] as JudgmentEnvelope;
    return [
      envelope(base, 901, 'jev-latest', 'none'),
      envelope(base, 902, 'jev-1.13.0', 'typesafe'),
      envelope(base, 903, null, null),
    ];
  }

  it("JudgmentTable: '모델' 열 — provider 'none' 은 '로컬' 배지(비용 없음 안내), 그 밖은 provider, 없으면 '기록 없음'", async () => {
    renderWithProviders(<JudgmentTable judgments={await rows()} caption="log" />);
    const table = screen.getByRole('table', { name: 'log' });
    expect(
      within(table).getByRole('columnheader', { name: t('page.G3.judgment.model') }),
    ).toBeInTheDocument();
    const local = within(table).getByTestId('judgment-model-901');
    expect(local).toHaveTextContent('jev-latest');
    expect(within(local).getByText(t('page.G3.judgment.local'))).toHaveAttribute(
      'title',
      t('page.G3.judgment.localHint'),
    );
    const real = within(table).getByTestId('judgment-model-902');
    expect(real).toHaveTextContent('jev-1.13.0');
    expect(real).toHaveTextContent(t('page.G3.judgment.provider', { provider: 'typesafe' }));
    expect(within(real).queryByText(t('page.G3.judgment.local'))).toBeNull();
    expect(within(table).getByTestId('judgment-model-903')).toHaveTextContent(
      t('page.G3.judgment.modelNone'),
    );
  });

  it('G7 판정 로그(GET /ops/judgments items)에 모델·로컬 표시', async () => {
    const items = await rows();
    const ops = await example<JudgmentOps>('/ops/judgments');
    server.use(http.get(mswPath('/ops/judgments'), () => HttpResponse.json({ ...ops, items })));
    renderRoute('/ops');
    const table = await screen.findByRole('table', { name: t('page.G7.stats') });
    expect(await within(table).findByTestId('judgment-model-901')).toHaveTextContent(
      t('page.G3.judgment.local'),
    );
  });

  it('G3 판정 로그 탭(단지 상세 judgments[])에도 같은 열', async () => {
    const detail = await example<ComplexDetail>('/complexes/2');
    const base = detail.judgments[0] as JudgmentEnvelope;
    server.use(
      http.get(mswPath('/complexes/:id'), () =>
        HttpResponse.json({
          ...detail,
          judgments: [envelope(base, 911, 'jev-latest', 'none')],
        }),
      ),
    );
    renderRoute('/complexes/2#judgments');
    expect(await screen.findByTestId('judgment-model-911')).toHaveTextContent(
      t('page.G3.judgment.local'),
    );
  });
});

describe('F2(D18-2) G7 real_calls = 판정기로 실제 보낸 tools/call 수', () => {
  it('통계 타일 아래 안내: 실제 호출의 뜻과 호출 = 실제 + 캐시', async () => {
    renderRoute('/ops');
    expect(await screen.findByTestId('judgment-real-hint')).toHaveTextContent(
      t('page.G7.stat.realHint'),
    );
  });
});

describe('F3·F4(D20-1) G0 청약홈 조회 기간(고급) → POST /regions applyhome_query', () => {
  async function pickAndName(): Promise<void> {
    const search = await screen.findByRole('searchbox', { name: t('page.G0.search') });
    await userEvent.type(search, '검단');
    const list = await screen.findByRole('list', { name: t('page.G0.candidates') });
    await userEvent.click(within(list).getAllByRole('checkbox')[0] as HTMLElement);
    await userEvent.type(screen.getByLabelText(t('page.G0.name')), '내 지역');
  }

  async function openWindow(): Promise<HTMLElement> {
    const group = await screen.findByRole('group', { name: t('page.G0.window.title') });
    await userEvent.click(within(group).getByText(t('page.G0.window.title')));
    return group;
  }

  it('기본은 비움 — 안내(지난 24개월 + 향후 12개월), 본문에 applyhome_query 없음', async () => {
    const rec = recordRequests();
    renderRoute('/regions/new');
    await pickAndName();
    const group = await openWindow();
    expect(within(group).getByText(t('page.G0.window.hint'))).toBeInTheDocument();
    expect(within(group).getByLabelText(t('page.G0.window.from'))).toHaveValue('');
    expect(within(group).getByLabelText(t('page.G0.window.to'))).toHaveValue('');
    await userEvent.click(screen.getByRole('button', { name: t('page.G0.start') }));
    await waitFor(() => expect(matching(rec.requests, 'POST', '/regions')).toHaveLength(1));
    const body = (await matching(rec.requests, 'POST', '/regions')[0]?.body) as Record<
      string,
      unknown
    >;
    expect('applyhome_query' in body).toBe(false);
    rec.stop();
  });

  it("입력하면 그 키만 보낸다: from_ym·to_ym 'YYYY-MM'", async () => {
    const rec = recordRequests();
    renderRoute('/regions/new');
    await pickAndName();
    const group = await openWindow();
    await userEvent.type(within(group).getByLabelText(t('page.G0.window.from')), '2024-10');
    await userEvent.click(screen.getByRole('button', { name: t('page.G0.start') }));
    await waitFor(() => expect(matching(rec.requests, 'POST', '/regions')).toHaveLength(1));
    const first = (await matching(rec.requests, 'POST', '/regions')[0]?.body) as {
      applyhome_query?: Record<string, unknown>;
    };
    expect(first.applyhome_query).toEqual({ from_ym: '2024-10' });
    rec.stop();
  });

  it('두 칸 모두 → {from_ym, to_ym}', async () => {
    const rec = recordRequests();
    renderRoute('/regions/new');
    await pickAndName();
    const group = await openWindow();
    await userEvent.type(within(group).getByLabelText(t('page.G0.window.from')), '2024-10');
    await userEvent.type(within(group).getByLabelText(t('page.G0.window.to')), '2027-03');
    await userEvent.click(screen.getByRole('button', { name: t('page.G0.start') }));
    await waitFor(() => expect(matching(rec.requests, 'POST', '/regions')).toHaveLength(1));
    const body = (await matching(rec.requests, 'POST', '/regions')[0]?.body) as {
      applyhome_query?: Record<string, unknown>;
    };
    expect(body.applyhome_query).toEqual({ from_ym: '2024-10', to_ym: '2027-03' });
    rec.stop();
  });

  it("형식이 틀리면(월 13·'2024/10') 칸 안내 + 시작 막힘(POST 없음), 시작 > 끝도 막힘", async () => {
    const rec = recordRequests();
    renderRoute('/regions/new');
    await pickAndName();
    const group = await openWindow();
    const from = within(group).getByLabelText(t('page.G0.window.from'));
    const start = screen.getByRole('button', { name: t('page.G0.start') });
    await userEvent.type(from, '2024-13');
    expect(within(group).getByText(t('page.G0.window.invalid'))).toBeInTheDocument();
    expect(start).toBeDisabled();
    await userEvent.clear(from);
    await userEvent.type(from, '2024/10');
    expect(start).toBeDisabled();
    await userEvent.clear(from);
    await userEvent.type(from, '2027-04');
    await userEvent.type(within(group).getByLabelText(t('page.G0.window.to')), '2027-03');
    expect(within(group).getByText(t('page.G0.window.order'))).toBeInTheDocument();
    expect(start).toBeDisabled();
    await userEvent.click(start);
    expect(matching(rec.requests, 'POST', '/regions')).toHaveLength(0);
    rec.stop();
  });

  it('서버 422(applyhome_query 칸) → 조회 기간 칸에 서버 안내', async () => {
    server.use(
      http.post(mswPath('/regions'), () =>
        HttpResponse.json(
          {
            code: 'validation_error',
            detail: "applyhome_query.from_ym: '2024-10' does not match",
            field_errors: [
              { loc: ['body', 'applyhome_query', 'from_ym'], msg: 'does not match pattern' },
            ],
          },
          { status: 422 },
        ),
      ),
    );
    renderRoute('/regions/new');
    await pickAndName();
    const group = await openWindow();
    await userEvent.type(within(group).getByLabelText(t('page.G0.window.from')), '2024-10');
    await userEvent.click(screen.getByRole('button', { name: t('page.G0.start') }));
    expect(
      await within(group).findByText(
        t('page.G0.window.server', { detail: 'does not match pattern' }),
      ),
    ).toBeInTheDocument();
  });

  it('목: 형식이 틀리면 422 validation_error(field_errors loc), 맞으면 201 + region.applyhome_query 그대로', async () => {
    const body = (q: unknown) =>
      JSON.stringify({
        name: 'x',
        query_text: 'x',
        selections: [{ kind: 'sigungu', code: '28260', full_name: 'x' }],
        applyhome_query: q,
      });
    const bad = await mock('/regions', { method: 'POST', body: body({ from_ym: '2024-13' }) });
    expect(bad.status).toBe(422);
    const err = (await bad.json()) as { code: string; field_errors: { loc: unknown[] }[] };
    expect(err.code).toBe('validation_error');
    expect(err.field_errors[0]?.loc).toEqual(['body', 'applyhome_query', 'from_ym']);
    const ok = await mock('/regions', {
      method: 'POST',
      body: body({ from_ym: '2024-10', to_ym: '2027-03' }),
    });
    expect(ok.status).toBe(201);
    const created = (await ok.json()) as RegionCreated;
    expect(created.region.applyhome_query).toEqual({ from_ym: '2024-10', to_ym: '2027-03' });
  });
});

describe('F5(D20-2) 트랙 (A) 공고 예정 후보 — G1·G2·G3', () => {
  it("G3 머리: applyhome_id null + track A → '공고 예정 후보(청약홈 미등록)', 범위 '보류 — 공고 후 재판정'", async () => {
    const detail = await example<ComplexDetail>('/complexes/2');
    const unknownFact = (unit: string) => ({
      v: null,
      label: '확인 불가' as const,
      reason: '공고 전',
      prov: null,
      checked_at: '2026-10-07',
      unit,
    });
    server.use(
      http.get(mswPath('/complexes/:id'), () =>
        HttpResponse.json({
          ...detail,
          header: {
            ...detail.header,
            id: 15,
            applyhome_id: null,
            name: '공고 예정 후보 단지',
            track: 'A',
            address: null,
            official_site_url: null,
            notice_date: unknownFact('date'),
          },
          price: {
            ...detail.price,
            price_low: unknownFact('won'),
            price_high: unknownFact('won'),
            discount: null,
          },
          intake_current: null,
          score: detail.score
            ? {
                ...detail.score,
                complex_id: 15,
                judge_scope: '보류',
                rank: null,
                total: {
                  v: null,
                  label: '확인 불가',
                  reason: '미판정',
                  prov: null,
                  checked_at: null,
                },
              }
            : null,
        }),
      ),
    );
    renderRoute('/complexes/15');
    const head = await screen.findByRole('region', { name: '공고 예정 후보 단지' });
    expect(within(head).getByTestId('upcoming-badge')).toHaveTextContent(
      t('page.G3.header.upcoming'),
    );
    expect(within(head).getByTestId('judge-scope')).toHaveTextContent(
      t('page.common.judgeScope.보류'),
    );
    expect(within(head).getAllByText(preNotice).length).toBeGreaterThan(0);
  });

  it('G3 머리: 청약홈 공고 단지(applyhome_id 있음)에는 배지 없음', async () => {
    renderRoute('/complexes/2');
    const detail = await example<ComplexDetail>('/complexes/2');
    const head = await screen.findByRole('region', { name: detail.header.name });
    expect(within(head).queryByTestId('upcoming-badge')).toBeNull();
  });

  it("G2 행(예시 complex 15, track A·보류): '보류 — 공고 후 재판정' 배지·'확인 불가(공고 전)'", async () => {
    renderRoute('/complexes');
    const link = await screen.findByRole('link', { name: '계양신도시 카이브 유보라' });
    const row = link.closest('tr') as HTMLElement;
    expect(within(row).getByTestId('judge-scope')).toHaveTextContent(
      t('page.common.judgeScope.보류'),
    );
    expect(within(row).getAllByText(preNotice).length).toBeGreaterThan(0);
  });

  it("G2 마지막 변경: field 'track' → '공고 예정 후보'", async () => {
    const page = await example<ComplexRowPage>('/snapshots/12/complexes');
    const first = page.items[0]!;
    server.use(
      http.get(mswPath('/snapshots/:sid/complexes'), () =>
        HttpResponse.json({
          ...page,
          items: [
            {
              ...first,
              last_change: { at: '2026-10-08T09:00:00+09:00', field: 'track', severity: 'notice' },
            },
          ],
          total: 1,
        }),
      ),
    );
    renderRoute('/complexes');
    const link = await screen.findByRole('link', { name: first.name });
    const row = link.closest('tr') as HTMLElement;
    expect(within(row).getByText(t('page.common.changeField.track'))).toBeInTheDocument();
  });
});

describe('F5·F7 G1 최근 변경 — 공고 예정 후보·합침·첫 적재 한 줄', () => {
  function ev(
    partial: Partial<ChangeEvent> & Pick<ChangeEvent, 'id' | 'entity' | 'field'>,
  ): ChangeEvent {
    return {
      snapshot_id: 12,
      entity_id: null,
      old_text: null,
      new_text: null,
      detected_at: '2026-10-08T09:00:00+09:00',
      severity: 'info',
      triggers_rejudge: false,
      complex_id: null,
      complex_name: null,
      tab: null,
      ...partial,
    };
  }

  async function useChanges(changes: ChangeEvent[]): Promise<void> {
    const dash = await example<Dashboard>('/snapshots/12/dashboard');
    server.use(
      http.get(mswPath('/snapshots/:sid/dashboard'), () => HttpResponse.json({ ...dash, changes })),
    );
  }

  it("region·first_load → '지역 · 첫 적재' + 요약 문장만(빈 값 화살표 없음), 정보 배지", async () => {
    const summary = '첫 적재: 단지 17개, 값 300건(빈 값 → 값 — 변경 이벤트 대신 요약)';
    await useChanges([
      ev({ id: 1, entity: 'region', entity_id: 1, field: 'first_load', new_text: summary }),
    ]);
    renderRoute('/');
    const feed = await screen.findByRole('list', { name: t('page.G1.changes') });
    const item = within(feed).getAllByRole('listitem')[0] as HTMLElement;
    expect(within(item).getByText(t('page.common.changeEntity.region'))).toBeInTheDocument();
    expect(within(item).getByText(t('page.common.changeField.first_load'))).toBeInTheDocument();
    expect(within(item).getByText(summary)).toBeInTheDocument();
    expect(item).not.toHaveTextContent(`${t('page.common.none')} →`);
    expect(item).not.toHaveTextContent('first_load');
    expect(item).not.toHaveTextContent('region');
    expect(within(item).getByText(t('page.common.severity.info'))).toBeInTheDocument();
  });

  it("complex·track(공고 예정 후보) → 단지 이름 + '공고 예정 후보', G3 링크 / applyhome_id 합침 → '주택관리번호'", async () => {
    await useChanges([
      ev({
        id: 2,
        entity: 'complex',
        entity_id: 15,
        field: 'track',
        new_text: 'A 공고 예정 후보 X(언론, 청약홈 미등록)',
        severity: 'notice',
        complex_id: 15,
        complex_name: '공고 예정 후보 단지',
      }),
      ev({
        id: 3,
        entity: 'notice',
        entity_id: 15,
        field: 'applyhome_id',
        new_text: '2026000999 X(공고 예정 후보와 합침)',
        severity: 'critical',
        triggers_rejudge: true,
        complex_id: 15,
        complex_name: '공고 예정 후보 단지',
      }),
    ]);
    renderRoute('/');
    const feed = await screen.findByRole('list', { name: t('page.G1.changes') });
    const [track, merged] = within(feed).getAllByRole('listitem') as HTMLElement[];
    // R9-UI P2: 필드 이름은 쉬운 문장 '{field} 변경' 안에
    expect(
      within(track!).getByText(
        t('page.G1.changeSentence', { field: t('page.common.changeField.track') }),
      ),
    ).toBeInTheDocument();
    expect(track).not.toHaveTextContent(/\btrack\b/);
    expect(within(track!).getByRole('link')).toHaveAttribute(
      'href',
      expect.stringMatching(/^\/complexes\/15/),
    );
    expect(
      within(merged!).getByText(
        t('page.G1.changeSentence', { field: t('page.common.changeField.applyhome_id') }),
      ),
    ).toBeInTheDocument();
    expect(within(merged!).getByText(t('page.common.severity.critical'))).toBeInTheDocument();
  });
});
