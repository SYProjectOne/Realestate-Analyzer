import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { TOKEN_STORAGE_KEY } from '@/api/auth';
import type { ClaimView } from '@/api/types';
import { t } from '@/i18n';
import { resetMockState } from '@/mocks/handlers.extra';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { renderRoute } from '@/test/render';
import { matching, recordRequests } from '../_shared/testing';

vi.mock('@/charts/EChartRuntime', () => ({ default: () => null }));
beforeEach(() => resetMockState());

const base: ClaimView = {
  id: 6990,
  snapshot_id: 12,
  section: 'complex:11',
  complex_id: 11,
  complex_name: '고촌센트럴자이',
  text: '고촌센트럴자이의 +10% 이상 명제는 likely로 판정되었다.',
  evidence_text: 'jl_120: +10% 0.11 unlikely(auto)',
  verify_status: 'contradicted',
  judgment_seq: 131,
  prov: 'jl_131',
  parent_claim_id: null,
  ordinal: 0,
  child_count: 0,
  remaining: true,
  pending_job_id: null,
  entity: null,
  entity_id: null,
  field: null,
  field_name: null,
  demotion: null,
};

function useClaims(rows: ClaimView[]) {
  server.use(http.get(mswPath('/snapshots/:sid/claims'), () => HttpResponse.json(rows)));
}

async function claimsSection() {
  return screen.findByRole('region', { name: t('page.G7.claims.title') });
}

describe('M8 G7 contradicted 주장 목록·문장 수정', () => {
  it('GET /snapshots/{sid}/claims(상태 필터 없음 — 계약 .22 A5) → 모순 줄의 문장·단지·근거·상태·남음 배지', async () => {
    const rec = recordRequests();
    renderRoute('/ops');
    const section = await claimsSection();
    const item = await within(section).findByTestId('claim-6990');
    expect(item).toHaveTextContent('고촌센트럴자이');
    expect(item).toHaveTextContent(/likely로 판정되었고/);
    expect(item).toHaveTextContent(/jl_120: \+10% 0\.11 unlikely/);
    expect(item).toHaveTextContent(t('page.G7.claims.status.contradicted'));
    expect(within(item).getByTestId('claim-remaining')).toHaveTextContent(
      t('page.G7.claims.remaining'),
    );
    await waitFor(() => expect(matching(rec.requests, 'GET', /\/claims$/)).toHaveLength(1));
    const req = matching(rec.requests, 'GET', /\/claims$/)[0];
    expect(req?.url.pathname).toMatch(/\/snapshots\/\d+\/claims$/);
    expect(req?.url.searchParams.get('status')).toBeNull();
    rec.stop();
  });

  it('출처 버튼(prov jl_) → 공통 출처 패널이 열린다', async () => {
    renderRoute('/ops');
    const item = await within(await claimsSection()).findByTestId('claim-6990');
    await userEvent.click(within(item).getByRole('button', { name: t('page.G7.claims.prov') }));
    const dialog = await screen.findByRole('dialog', { name: t('provenance.title') });
    expect(dialog).toHaveAttribute('data-prov', 'jl_131');
  });

  it('문장 수정 → PATCH /claims/{id} {text} → claim.reverify 잡 진행 표시', async () => {
    useClaims([base]);
    const rec = recordRequests();
    renderRoute('/ops');
    const item = await within(await claimsSection()).findByTestId('claim-6990');
    const box = within(item).getByLabelText(t('page.G7.claims.revise'));
    expect(box).toHaveValue(base.text);
    await userEvent.clear(box);
    await userEvent.type(box, '고친 문장이다.');
    await userEvent.click(within(item).getByRole('button', { name: t('page.G7.claims.submit') }));
    await waitFor(() => expect(matching(rec.requests, 'PATCH', '/claims/6990')).toHaveLength(1));
    expect(await matching(rec.requests, 'PATCH', '/claims/6990')[0]?.body).toEqual({
      text: '고친 문장이다.',
    });
    const progress = await within(item).findByTestId('claim-job');
    expect(await within(progress).findByText(t('job.name.claim_reverify'))).toBeInTheDocument();
    rec.stop();
  });

  it('같은 문장이거나 비어 있으면 보내지 않는다', async () => {
    useClaims([base]);
    renderRoute('/ops');
    const item = await within(await claimsSection()).findByTestId('claim-6990');
    expect(within(item).getByRole('button', { name: t('page.G7.claims.submit') })).toBeDisabled();
    await userEvent.clear(within(item).getByLabelText(t('page.G7.claims.revise')));
    expect(within(item).getByRole('button', { name: t('page.G7.claims.submit') })).toBeDisabled();
  });

  it('409 conflict → 서버 detail 을 보인다', async () => {
    useClaims([base]);
    server.use(
      http.patch(mswPath('/claims/:id'), () =>
        HttpResponse.json({ code: 'conflict', detail: '이미 분할된 주장입니다' }, { status: 409 }),
      ),
    );
    renderRoute('/ops');
    const item = await within(await claimsSection()).findByTestId('claim-6990');
    await userEvent.type(within(item).getByLabelText(t('page.G7.claims.revise')), ' 수정');
    await userEvent.click(within(item).getByRole('button', { name: t('page.G7.claims.submit') }));
    expect(await within(item).findByRole('alert')).toHaveTextContent('이미 분할된 주장입니다');
  });

  it('pending_job_id 가 있거나 child_count>0 이면 수정 칸·버튼이 꺼진다', async () => {
    useClaims([
      { ...base, id: 1, pending_job_id: 931 },
      { ...base, id: 2, child_count: 2, remaining: false },
    ]);
    renderRoute('/ops');
    const section = await claimsSection();
    const pending = await within(section).findByTestId('claim-1');
    expect(within(pending).getByLabelText(t('page.G7.claims.revise'))).toBeDisabled();
    expect(
      within(pending).getByRole('button', { name: t('page.G7.claims.submit') }),
    ).toBeDisabled();
    expect(pending).toHaveTextContent(t('page.G7.claims.pending', { job: '#931' }));
    const split = within(section).getByTestId('claim-2');
    expect(within(split).getByLabelText(t('page.G7.claims.revise'))).toBeDisabled();
    expect(split).toHaveTextContent(t('page.G7.claims.split', { n: '2' }));
    expect(within(split).queryByTestId('claim-remaining')).toBeNull();
  });

  it('읽기 전용 토큰이면 수정이 꺼진다', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-read');
    window.localStorage.setItem('sa.token.role', 'read');
    useClaims([base]);
    renderRoute('/ops');
    const item = await within(await claimsSection()).findByTestId('claim-6990');
    expect(within(item).getByLabelText(t('page.G7.claims.revise'))).toBeDisabled();
    const button = within(item).getByRole('button', { name: t('page.G7.claims.submit') });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute('title', t('auth.readOnlyHint'));
  });

  it('409 conflict 뒤 목록을 다시 불러와 낡은 행을 갱신한다', async () => {
    let calls = 0;
    server.use(
      http.get(mswPath('/snapshots/:sid/claims'), () => {
        calls += 1;
        return HttpResponse.json(calls === 1 ? [base] : [{ ...base, pending_job_id: 777 }]);
      }),
      http.patch(mswPath('/claims/:id'), () =>
        HttpResponse.json(
          { code: 'conflict', detail: '같은 주장의 재검증 잡이 대기 중이다' },
          { status: 409 },
        ),
      ),
    );
    renderRoute('/ops');
    const item = await within(await claimsSection()).findByTestId('claim-6990');
    await userEvent.type(within(item).getByLabelText(t('page.G7.claims.revise')), ' 수정');
    await userEvent.click(within(item).getByRole('button', { name: t('page.G7.claims.submit') }));
    expect(await within(item).findByRole('alert')).toHaveTextContent('대기 중이다');
    await waitFor(() => expect(calls).toBeGreaterThanOrEqual(2));
    expect(
      await within(item).findByText(t('page.G7.claims.pending', { job: '#777' })),
    ).toBeInTheDocument();
    expect(within(item).getByLabelText(t('page.G7.claims.revise'))).toBeDisabled();
  });

  it('422(같은 대상 아님) → 서버 detail 을 그대로 보인다', async () => {
    useClaims([{ ...base, field: 'resale_months', field_name: '전매제한 기간' }]);
    const detail =
      "고친 문장은 원 주장과 같은 대상(단지·필드 '전매제한 기간')만 말해야 한다 — '입주 예정 시기' 용어가 있다";
    server.use(
      http.patch(mswPath('/claims/:id'), () =>
        HttpResponse.json(
          {
            code: 'validation_error',
            detail,
            field_errors: [{ loc: ['body', 'text'], msg: '같은 대상이 아니다' }],
          },
          { status: 422 },
        ),
      ),
    );
    renderRoute('/ops');
    const item = await within(await claimsSection()).findByTestId('claim-6990');
    await userEvent.type(within(item).getByLabelText(t('page.G7.claims.revise')), ' 입주');
    await userEvent.click(within(item).getByRole('button', { name: t('page.G7.claims.submit') }));
    expect(await within(item).findByRole('alert')).toHaveTextContent(detail);
  });
});

describe('D10-3 사실 주장 — 대상 필드 · 강등 상태', () => {
  const demotion = {
    id: 3,
    claim_id: 6991,
    entity: 'complex',
    entity_id: 11,
    field: 'resale_months',
    status: 'demoted' as const,
    label: '확인 불가' as const,
    reason: '검증 모순' as const,
    created_at: '2026-10-09T11:02:00+09:00',
    restored_at: null,
    restored_by: null,
    checklist_item_id: 58,
    rejudge_job_id: 9103,
  };
  const fact: ClaimView = {
    ...base,
    id: 6991,
    text: '고촌센트럴자이 전매제한 기간은 36개월이다',
    entity: 'complex',
    entity_id: 11,
    field: 'resale_months',
    field_name: '전매제한 기간',
    demotion: null,
  };

  it('대상 필드 이름과 "고치면 사실이 강등된다" 안내(사실 주장만)', async () => {
    useClaims([fact, base]);
    renderRoute('/ops');
    const section = await claimsSection();
    const item = await within(section).findByTestId('claim-6991');
    expect(within(item).getByTestId('claim-field')).toHaveTextContent(
      t('page.G7.claims.field', { name: '전매제한 기간' }),
    );
    expect(item).toHaveTextContent(t('page.G7.claims.demoteHint'));
    const plain = within(section).getByTestId('claim-6990');
    expect(within(plain).queryByTestId('claim-field')).toBeNull();
    expect(plain).not.toHaveTextContent(t('page.G7.claims.demoteHint'));
  });

  it('강등됨 → "확인 불가(검증 모순)" 배지', async () => {
    useClaims([{ ...fact, demotion }]);
    renderRoute('/ops');
    const item = await within(await claimsSection()).findByTestId('claim-6991');
    expect(within(item).getByTestId('claim-demotion')).toHaveTextContent('확인 불가(검증 모순)');
  });

  it.each([
    ['human_check', '되돌림(사람 확인)'],
    ['new_source', '되돌림(새 원문)'],
    [null, '되돌림'],
  ] as const)('복원됨(restored_by=%s) → "%s"', async (by, text) => {
    useClaims([
      {
        ...fact,
        demotion: {
          ...demotion,
          status: 'restored',
          restored_by: by,
          restored_at: '2026-10-10T09:00:00+09:00',
        },
      },
    ]);
    renderRoute('/ops');
    const item = await within(await claimsSection()).findByTestId('claim-6991');
    const badge = within(item).getByTestId('claim-demotion');
    expect(badge).toHaveTextContent(text);
    expect(badge).not.toHaveTextContent('검증 모순');
  });
});

describe('M8 G7 빈 목록', () => {
  it('contradicted 가 없으면 빈 안내', async () => {
    useClaims([]);
    renderRoute('/ops');
    const section = await claimsSection();
    expect(await within(section).findByText(t('page.G7.claims.none'))).toBeInTheDocument();
  });
});
