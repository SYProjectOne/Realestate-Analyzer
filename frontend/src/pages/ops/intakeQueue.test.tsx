/**
 * 계약 2026-10-09.19 · D26-2 — G7 접수 확인 대기열(GET /ops/intake-queue).
 *  - 서버가 묶은 분류·사유별 건수를 그대로 보인다(화면은 묶지 않는다 — 새 사유는 서버가 '기타'로)
 *  - 항목: 단지(G3 링크)·접수 배지·HTTP·확인 시각·근거 페이지·스크린샷·판정 로그 표식·반영 대기 사람 확인
 *  - '사람 확인 입력' → 같은 /ops 의 HumanCheckForm 을 그 단지·접수 상태로 채움 → 저장(POST) → 대기열 '반영 대기'
 */
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import type { IntakeQueue } from '@/api/types';
import { t } from '@/i18n';
import { resetMockState } from '@/mocks/handlers.extra';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { renderRoute } from '@/test/render';
import example from '../../../../contracts/examples/intake_queue.json';
import emptyExample from '../../../../contracts/examples/intake_queue_empty.json';
import { matching, recordRequests } from '../_shared/testing';

vi.mock('@/charts/EChartRuntime', () => ({ default: () => null }));
beforeEach(() => resetMockState());

const QUEUE = example.value as IntakeQueue;

async function queueSection() {
  return screen.findByRole('region', { name: t('page.G7.iq.title') });
}

function itemRow(section: HTMLElement, complexId: number): HTMLElement {
  const row = section.querySelector(`[data-testid="iq-item"][data-complex-id="${complexId}"]`);
  expect(row).not.toBeNull();
  return row as HTMLElement;
}

describe('G7 접수 확인 대기열(계약 .19)', () => {
  it('분류·사유별 건수 — 서버 순서 그대로, 판정 대상 아님·미정은 접어 둔다', async () => {
    const rec = recordRequests();
    renderRoute('/ops');
    const section = await queueSection();
    await within(section).findByTestId('intake-queue');
    expect(within(section).getByTestId('intake-queue-total')).toHaveTextContent(
      t('page.G7.iq.total', { n: '7' }),
    );
    const cats = [...section.querySelectorAll('details[data-testid^="iq-category-"]')];
    expect(cats.map((d) => d.getAttribute('data-testid'))).toEqual([
      'iq-category-collect_failed',
      'iq-category-identity',
      'iq-category-no_phrase',
      'iq-category-not_judged',
      'iq-category-undecided',
    ]);
    const open = cats.map((d) => (d as HTMLDetailsElement).open);
    expect(open).toEqual([true, true, true, false, false]);
    const failed = cats[0] as HTMLElement;
    expect(failed.querySelector('summary')).toHaveTextContent(
      t('page.G7.iq.category.collect_failed'),
    );
    const groups = within(failed).getAllByTestId('iq-group');
    expect(
      groups.map((g) => g.querySelector('[data-reason]')?.getAttribute('data-reason')),
    ).toEqual(['DNS', '403']);
    expect(groups[0]).toHaveTextContent(t('page.G7.iq.groupCount', { n: '2' }));
    // 기준 스냅샷 지정: 페이지의 스냅샷 id 를 넘기고 region_id 는 넘기지 않는다
    await waitFor(() => expect(matching(rec.requests, 'GET', '/ops/intake-queue').length).toBe(1));
    const url = matching(rec.requests, 'GET', '/ops/intake-queue')[0]!.url;
    expect(url.searchParams.get('snapshot')).toMatch(/^\d+$/);
    expect(url.searchParams.has('region_id')).toBe(false);
    rec.stop();
  });

  it('항목: G3 링크·접수 배지·HTTP·근거 페이지·스크린샷·판정 로그·반영 대기', async () => {
    renderRoute('/ops');
    const section = await queueSection();
    await within(section).findByTestId('intake-queue');
    const opus = itemRow(section, 4);
    expect(within(opus).getByRole('link', { name: '오퍼스 한강 스위첸' })).toHaveAttribute(
      'href',
      expect.stringMatching(/^\/complexes\/4(\?|$)/),
    );
    expect(within(opus).getByTestId('intake-badge')).toHaveTextContent('403');
    expect(opus.querySelector('[data-meta="status"]')).toHaveTextContent('403');
    expect(within(opus).getByRole('link', { name: t('page.G7.iq.evidence') })).toHaveAttribute(
      'href',
      'https://opus-switzen.com/',
    );
    expect(within(opus).queryByTestId('iq-screenshot')).toBeNull();
    expect(within(opus).queryByTestId('iq-pending')).toBeNull();
    // 문구로 판단 불가(헤드리스 스크린샷) — 스크린샷 미리보기·판정 로그 표식·반영 대기 사람 확인
    const educity = itemRow(section, 5);
    expect(within(educity).getByTestId('iq-screenshot')).toBeTruthy();
    expect(within(educity).getByTestId('iq-judgment')).toHaveTextContent(
      t('page.G7.iq.judgment', { ref: 'jl_445' }),
    );
    expect(within(educity).getByTestId('iq-pending')).toHaveTextContent(/가능/);
    // 근거 주소가 없는 항목
    const granter = itemRow(section, 1);
    expect(within(granter).getByText(t('page.G7.iq.noEvidence'))).toBeTruthy();
  });

  it("'사람 확인 입력' → 폼을 그 단지·접수 상태로 채움 → 저장하면 대기열에 반영 대기", async () => {
    const rec = recordRequests();
    const { router } = renderRoute('/ops');
    const section = await queueSection();
    await within(section).findByTestId('intake-queue');
    const opus = itemRow(section, 4);
    await userEvent.click(within(opus).getByTestId('iq-human-check'));
    await waitFor(() => {
      const params = new URLSearchParams(router.state.location.search);
      expect(params.get('hc_complex')).toBe('4');
      expect(params.get('hc_field')).toBe('intake_status');
    });
    expect(router.state.location.hash).toBe('#human-check');
    const form = await screen.findByRole('form', { name: t('page.G7.human') });
    const complex = within(form).getByLabelText(t('page.G7.hc.complex')) as HTMLSelectElement;
    await waitFor(() => expect(complex.value).toBe('4'));
    expect((within(form).getByLabelText(t('page.G7.hc.field')) as HTMLSelectElement).value).toBe(
      'intake_status',
    );
    await userEvent.selectOptions(within(form).getByLabelText(t('page.G7.hc.value')), '가능');
    await userEvent.selectOptions(within(form).getByLabelText(t('page.G7.hc.enteredBy')), '운영자');
    await userEvent.click(within(form).getByRole('button', { name: t('page.G7.hc.submit') }));
    await waitFor(() =>
      expect(matching(rec.requests, 'POST', '/ops/human-checks')).toHaveLength(1),
    );
    const body = (await matching(rec.requests, 'POST', '/ops/human-checks')[0]!.body) as Record<
      string,
      unknown
    >;
    expect(body).toMatchObject({ complex_id: 4, field: 'intake_status', value_text: '가능' });
    // 저장 뒤 대기열을 다시 읽는다 → 그 단지에 '사람 확인 입력됨 — 재판정·발행 대기'
    await waitFor(() =>
      expect(within(itemRow(section, 4)).getByTestId('iq-pending')).toHaveTextContent(/가능/),
    );
    expect(matching(rec.requests, 'GET', '/ops/intake-queue').length).toBeGreaterThanOrEqual(2);
    rec.stop();
  });

  it('스냅샷 없음 · 빈 대기열 안내', async () => {
    server.use(http.get(mswPath('/ops/intake-queue'), () => HttpResponse.json(emptyExample.value)));
    renderRoute('/ops');
    const section = await queueSection();
    expect(await within(section).findByText(t('page.G7.iq.noSnapshot'))).toBeTruthy();
    expect(within(section).queryByTestId('intake-queue-total')).toBeNull();
  });

  it('스냅샷은 있는데 확인할 행이 없으면 없음 안내', async () => {
    server.use(
      http.get(mswPath('/ops/intake-queue'), () =>
        HttpResponse.json({ ...QUEUE, total: 0, groups: [] } satisfies IntakeQueue),
      ),
    );
    renderRoute('/ops');
    const section = await queueSection();
    expect(await within(section).findByText(t('page.G7.iq.none'))).toBeTruthy();
  });

  it('모르는 사유(서버 other)도 그 사유 이름으로 보인다 — 화면은 사유를 해석하지 않는다', async () => {
    const other = {
      ...QUEUE,
      total: 1,
      groups: [
        {
          category: 'other' as const,
          reason: '새 수집 사유(R7-SITE)',
          count: 1,
          items: [{ ...QUEUE.groups[0]!.items[0]!, reason: '새 수집 사유(R7-SITE)' }],
        },
      ],
    } satisfies IntakeQueue;
    server.use(http.get(mswPath('/ops/intake-queue'), () => HttpResponse.json(other)));
    renderRoute('/ops');
    const section = await queueSection();
    const cat = await within(section).findByTestId('iq-category-other');
    expect(cat).toHaveTextContent(t('page.G7.iq.category.other'));
    expect(within(cat).getByTestId('iq-group')).toHaveTextContent('새 수집 사유(R7-SITE)');
  });
});
