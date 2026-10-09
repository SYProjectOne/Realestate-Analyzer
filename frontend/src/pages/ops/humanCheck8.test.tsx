/**
 * M-5(3차 리뷰) · D11-3 · 계약 .8 초안: 사람 확인 폼이 강등 가능한 사실 필드를 지정해 복원할 수 있다.
 *  - 필드 = 접수 상태 + 사실 5개(max_price_won·move_in_ym·resale_months·residency_months·down_payment_pct) + 기타
 *  - 값 형·범위·길이 검사(정수 필드 '6.02' 거부 — 절삭 금지), note ≤ 500, value ≤ 200
 *  - ClaimsPanel 강등 배지 옆 '사람 확인으로 복원' → 폼 미리 채움(단지·필드·사실 행) → 저장 → 강등 '복원됨(사람 확인)'
 */
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { ROLE_STORAGE_KEY, TOKEN_STORAGE_KEY } from '@/api/auth';
import { HUMAN_CHECK_FIELDS } from '@/api/contract8';
import type { ClaimView } from '@/api/types';
import { t } from '@/i18n';
import { resetMockState } from '@/mocks/handlers.extra';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { renderRoute } from '@/test/render';
import { matching, recordRequests } from '../_shared/testing';
import { validateHumanValue } from './HumanCheckForm';

vi.mock('@/charts/EChartRuntime', () => ({ default: () => null }));
beforeEach(() => resetMockState());

async function humanForm() {
  return screen.findByRole('form', { name: t('page.G7.human') });
}

async function pickComplex(form: HTMLElement, id: string) {
  const complex = within(form).getByLabelText(t('page.G7.hc.complex'));
  await waitFor(() => expect(complex.querySelector(`option[value="${id}"]`)).not.toBeNull());
  await userEvent.selectOptions(complex, id);
}

describe('M-5 사람 확인 필드(계약 .8)', () => {
  it('필드 선택지 = 접수 상태 + 강등 가능한 사실 5개 + 기타', async () => {
    renderRoute('/ops');
    const form = await humanForm();
    const select = within(form).getByLabelText(t('page.G7.hc.field'));
    const values = [...select.querySelectorAll('option')].map((o) => o.getAttribute('value'));
    expect(values).toEqual([...HUMAN_CHECK_FIELDS]);
    for (const f of HUMAN_CHECK_FIELDS) {
      expect(within(select).getByRole('option', { name: t(`page.G7.hcField.${f}`) })).toBeTruthy();
    }
  });

  it('값 형·범위: 정수 필드 6.02 거부(절삭 금지), 개월 0~240, 입주 YYYY-MM, 계약금 0~100', () => {
    expect(validateHumanValue('resale_months', '6.02')).toBe(t('page.G7.hc.badInt'));
    expect(validateHumanValue('resale_months', '12')).toBeNull();
    expect(validateHumanValue('residency_months', '241')).not.toBeNull();
    expect(validateHumanValue('move_in_ym', '2028-3')).toBe(t('page.G7.hc.badYm'));
    expect(validateHumanValue('move_in_ym', '2028-03')).toBeNull();
    expect(validateHumanValue('down_payment_pct', '10.5')).toBeNull();
    expect(validateHumanValue('down_payment_pct', '101')).not.toBeNull();
    expect(validateHumanValue('max_price_won', '605,000,000')).toBeNull();
    expect(validateHumanValue('other', 'x'.repeat(201))).not.toBeNull();
  });

  it('정수 필드에 소수 → 오류, POST 하지 않는다', async () => {
    const rec = recordRequests();
    renderRoute('/ops');
    const form = await humanForm();
    await pickComplex(form, '2');
    await userEvent.selectOptions(
      within(form).getByLabelText(t('page.G7.hc.field')),
      'resale_months',
    );
    await userEvent.type(within(form).getByLabelText(t('page.G7.hc.value')), '6.02');
    await userEvent.selectOptions(within(form).getByLabelText(t('page.G7.hc.enteredBy')), '운영자');
    await userEvent.click(within(form).getByRole('button', { name: t('page.G7.hc.submit') }));
    expect(await within(form).findByRole('alert')).toHaveTextContent(t('page.G7.hc.badInt'));
    expect(matching(rec.requests, 'POST', '/ops/human-checks')).toHaveLength(0);
    rec.stop();
  });

  it('메모·값 길이 상한(500·200)은 입력 칸이 막는다', async () => {
    renderRoute('/ops');
    const form = await humanForm();
    expect(within(form).getByLabelText(t('page.G7.hc.note'))).toHaveAttribute('maxlength', '500');
    await userEvent.selectOptions(within(form).getByLabelText(t('page.G7.hc.field')), 'other');
    expect(within(form).getByLabelText(t('page.G7.hc.value'))).toHaveAttribute('maxlength', '200');
  });

  it('사실 필드 저장 → POST field=move_in_ym, 결과 문구(접수 배지 아님)', async () => {
    const rec = recordRequests();
    renderRoute('/ops');
    const form = await humanForm();
    await pickComplex(form, '2');
    await userEvent.selectOptions(within(form).getByLabelText(t('page.G7.hc.field')), 'move_in_ym');
    const value = within(form).getByLabelText(t('page.G7.hc.value'));
    expect(value).toHaveAttribute('type', 'month');
    await userEvent.type(value, '2028-03');
    await userEvent.selectOptions(within(form).getByLabelText(t('page.G7.hc.enteredBy')), '검토자');
    await userEvent.click(within(form).getByRole('button', { name: t('page.G7.hc.submit') }));
    const result = await within(form).findByTestId('human-check-result');
    expect(result).toHaveTextContent(t('page.G7.hcField.move_in_ym'));
    expect(within(result).queryByTestId('intake-badge')).toBeNull();
    const posted = await matching(rec.requests, 'POST', '/ops/human-checks')[0]?.body;
    expect(posted).toMatchObject({ complex_id: 2, field: 'move_in_ym', value_text: '2028-03' });
    expect(posted).not.toHaveProperty('entity_id');
    rec.stop();
  });
});

describe('M-5 강등 사실 → 사람 확인으로 복원(D11-3)', () => {
  const demoted: ClaimView = {
    id: 6991,
    snapshot_id: 12,
    section: 'complex:11',
    complex_id: 11,
    complex_name: '고촌센트럴자이',
    text: '고촌센트럴자이 전매제한 기간은 36개월이다',
    evidence_text: null,
    verify_status: 'contradicted',
    judgment_seq: 131,
    prov: 'jl_131',
    parent_claim_id: null,
    ordinal: 0,
    child_count: 0,
    remaining: true,
    pending_job_id: null,
    entity: 'complex',
    entity_id: 11,
    field: 'resale_months',
    field_name: '전매제한 기간',
    demotion: {
      id: 3,
      claim_id: 6991,
      entity: 'complex',
      entity_id: 11,
      field: 'resale_months',
      status: 'demoted',
      label: '확인 불가',
      reason: '검증 모순',
      created_at: '2026-10-09T11:02:00+09:00',
      restored_at: null,
      restored_by: null,
      checklist_item_id: 58,
      rejudge_job_id: 9103,
    },
  };

  it('복원 링크 → 폼 미리 채움 → 저장(entity_id) → 주장 목록 다시 읽어 "복원됨(사람 확인)"', async () => {
    let restored = false;
    server.use(
      http.get(mswPath('/snapshots/:sid/claims'), () =>
        HttpResponse.json([
          restored
            ? {
                ...demoted,
                demotion: {
                  ...demoted.demotion!,
                  status: 'restored',
                  restored_by: 'human_check',
                  restored_at: '2026-10-10T09:00:00+09:00',
                },
              }
            : demoted,
        ]),
      ),
    );
    const rec = recordRequests();
    const { router } = renderRoute('/ops');
    const section = await screen.findByRole('region', { name: t('page.G7.claims.title') });
    const item = await within(section).findByTestId('claim-6991');
    await userEvent.click(within(item).getByTestId('claim-restore-human'));
    await waitFor(() => expect(router.state.location.search).toContain('hc_field=resale_months'));
    expect(router.state.location.hash).toBe('#human-check');

    const form = await humanForm();
    await waitFor(() =>
      expect(within(form).getByLabelText(t('page.G7.hc.complex'))).toHaveValue('11'),
    );
    expect(within(form).getByLabelText(t('page.G7.hc.field'))).toHaveValue('resale_months');
    expect(within(form).getByTestId('hc-entity')).toBeInTheDocument();
    await userEvent.type(within(form).getByLabelText(t('page.G7.hc.value')), '12');
    await userEvent.selectOptions(within(form).getByLabelText(t('page.G7.hc.enteredBy')), '운영자');
    restored = true;
    await userEvent.click(within(form).getByRole('button', { name: t('page.G7.hc.submit') }));

    await waitFor(() =>
      expect(matching(rec.requests, 'POST', '/ops/human-checks')).toHaveLength(1),
    );
    expect(await matching(rec.requests, 'POST', '/ops/human-checks')[0]?.body).toMatchObject({
      complex_id: 11,
      field: 'resale_months',
      entity_id: 11,
      value_text: '12',
    });
    // 저장 → 사실 화면 무효화(minor 15) → 주장 목록 다시 읽기 → 복원됨
    await waitFor(() =>
      expect(within(section).getByTestId('claim-demotion')).toHaveTextContent('복원됨(사람 확인)'),
    );
    expect(within(section).queryByTestId('claim-restore-human')).toBeNull();
    rec.stop();
  });

  it('읽기 전용(쓰기 불가)이면 복원 링크가 없다', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-r');
    window.localStorage.setItem(ROLE_STORAGE_KEY, 'read');
    server.use(http.get(mswPath('/snapshots/:sid/claims'), () => HttpResponse.json([demoted])));
    renderRoute('/ops');
    const section = await screen.findByRole('region', { name: t('page.G7.claims.title') });
    const item = await within(section).findByTestId('claim-6991');
    expect(within(item).queryByTestId('claim-restore-human')).toBeNull();
  });
});
