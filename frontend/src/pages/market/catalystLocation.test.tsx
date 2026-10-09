/**
 * D11-5(계약 .8): 호재 위치 확인 UI — PATCH /catalysts/{id} → CatalystUpdated {catalyst, links, job}.
 * 좌표 없는 단지는 거리 '확인 불가(<서버 reason>)'·가중치 1(비수치 메타)·연결 근거(reason 필수), 위치 미확정이면 링크 없음.
 * 응답 job(연결이 바뀌면 rejudge, 그대로면 null)을 보인다. 생성 핸들러(계약 예시 catalyst_updated.json)를 그대로 쓰고,
 * 상태가 필요한 흐름만 server.use 로 덮는다.
 */
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { getResponse, http, HttpResponse, type RequestHandler } from 'msw';
import type { CatalystUpdated, JobRun, Market } from '@/api/types';
import { t } from '@/i18n';
import { resetMockState } from '@/mocks/handlers.extra';
import { generatedHandlers } from '@/mocks/handlers.gen';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { renderRoute } from '@/test/render';
import { matching, recordRequests } from '../_shared/testing';
import { parseCoord, parseYm } from './CatalystLocationPanel';

vi.mock('@/charts/EChartRuntime', () => ({ default: () => null }));
beforeEach(() => resetMockState());

async function panel() {
  return screen.findByRole('region', { name: t('page.G6.loc.title') });
}

async function row(name: string) {
  const list = within(await panel()).getByRole('list', { name: t('page.G6.loc.title') });
  return (await within(list).findByText(name)).closest('li') as HTMLElement;
}

/** 생성 핸들러(계약 예시) JSON */
async function example<T>(path: string, method = 'GET'): Promise<T> {
  const res = await getResponse(
    generatedHandlers as RequestHandler[],
    new Request(new URL(`/api${path}`, 'http://localhost').toString(), {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: method === 'GET' ? undefined : '{}',
    }),
  );
  return (await res!.json()) as T;
}

async function openForm(name: string) {
  const item = await row(name);
  await userEvent.click(within(item).getByRole('button', { name: t('page.G6.loc.open') }));
  return {
    item,
    form: within(item).getByRole('form', { name: t('page.G6.loc.formFor', { name }) }),
  };
}

async function pickFirstComplex(form: HTMLElement) {
  const select = within(form).getByLabelText(t('page.G6.loc.complexes'));
  await waitFor(() => expect(select.querySelectorAll('option').length).toBeGreaterThan(1));
  const first = select.querySelectorAll('option')[0] as HTMLOptionElement;
  await userEvent.selectOptions(select, first.value);
  return first;
}

describe('D11-5 호재 위치 확인(계약 .8)', () => {
  it('좌표·예상 시기 검사: 범위·형식, 빈 값 허용', () => {
    expect(parseCoord('', 'lat')).toBeNull();
    expect(parseCoord('37.55', 'lat')).toBe(37.55);
    expect(parseCoord('91', 'lat')).toBe('invalid');
    expect(parseCoord('126.7', 'lon')).toBe(126.7);
    expect(parseCoord('abc', 'lon')).toBe('invalid');
    expect(parseYm('')).toBeNull();
    expect(parseYm('2031-12')).toBe('2031-12');
    expect(parseYm('2031-13')).toBe('invalid');
  });

  it('단지 선택 → PATCH → 응답 links 표(거리 확인 불가 + 서버 reason · 가중치 · 연결 근거), job=null 안내', async () => {
    const rec = recordRequests();
    renderRoute('/market');
    const { item, form } = await openForm('GTX-B');
    expect(within(item).getByTestId('loc-status')).toHaveTextContent(t('page.G6.loc.unconfirmed'));
    const first = await pickFirstComplex(form);
    await userEvent.click(within(form).getByRole('button', { name: t('page.G6.loc.submit') }));

    await waitFor(() => expect(matching(rec.requests, 'PATCH', '/catalysts/50')).toHaveLength(1));
    expect(await matching(rec.requests, 'PATCH', '/catalysts/50')[0]?.body).toEqual({
      location_confirmed: true,
      living_area_ids: [],
      complex_ids: [Number(first.value)],
    });
    // 계약 예시 응답: 단지 2(사람 지정)·5(같은 생활권), 좌표 없음 → distance null·weight 1·추정, job null
    const expected = await example<CatalystUpdated>('/catalysts/50', 'PATCH');
    const links = await within(await panel()).findByTestId('catalyst-links');
    const rows = within(links).getAllByRole('row').slice(1);
    expect(rows).toHaveLength(expected.links.length);
    expected.links.forEach((link, i) => {
      const r = rows[i] as HTMLElement;
      expect(r).toHaveTextContent(link.reason ?? '');
      expect(r.querySelector('[data-meta="derived"]')).toHaveTextContent('1.00');
      expect(within(r).getAllByText(link.reason ?? '').length).toBeGreaterThan(0);
    });
    expect(rows[0]).toHaveTextContent('엘리프 검단 포레듀');
    expect(within(await panel()).getByTestId('catalyst-job-none')).toHaveTextContent(
      t('page.G6.loc.noJob'),
    );
    rec.stop();
  });

  it('연결이 바뀌면 응답 job(rejudge) 진행 표시 + 시장 다시 읽기 → "위치 확인됨"', async () => {
    let confirmed = false;
    server.use(
      http.patch(mswPath('/catalysts/:id'), async () => {
        confirmed = true;
        const base = await example<CatalystUpdated>('/catalysts/50', 'PATCH');
        const job = await example<JobRun>('/jobs/9100');
        return HttpResponse.json({
          ...base,
          catalyst: { ...base.catalyst, id: 50, name: 'GTX-B', location_confirmed: true },
          job: { ...job, id: 9100, job_name: 'rejudge', kind: 'rejudge' },
        } satisfies CatalystUpdated);
      }),
      http.get(mswPath('/snapshots/:sid/market'), async () => {
        const market = await example<Market>('/snapshots/12/market');
        return HttpResponse.json({
          ...market,
          catalysts: market.catalysts.map((c) =>
            c.id === 50 && confirmed ? { ...c, location_confirmed: true, linked: true } : c,
          ),
        } satisfies Market);
      }),
    );
    renderRoute('/market');
    const { form } = await openForm('GTX-B');
    await pickFirstComplex(form);
    await userEvent.click(within(form).getByRole('button', { name: t('page.G6.loc.submit') }));
    const job = await within(await panel()).findByTestId('catalyst-job');
    expect(await within(job).findByText('rejudge')).toBeInTheDocument();
    await waitFor(async () =>
      expect(within(await row('GTX-B')).getByTestId('loc-status')).toHaveTextContent(
        t('page.G6.loc.confirmed'),
      ),
    );
  });

  it('대상 없이 저장·위도만·범위 밖·좌표만(영향 범위 없음) → 오류, PATCH 없음', async () => {
    const rec = recordRequests();
    renderRoute('/market');
    const { form } = await openForm('GTX-B');
    const submit = within(form).getByRole('button', { name: t('page.G6.loc.submit') });
    await userEvent.click(submit);
    expect(within(form).getByRole('alert')).toHaveTextContent(t('page.G6.loc.needTarget'));
    const lat = within(form).getByLabelText(t('page.G6.loc.lat'));
    const lon = within(form).getByLabelText(t('page.G6.loc.lon'));
    await userEvent.type(lat, '37.5');
    await userEvent.click(submit);
    expect(within(form).getByRole('alert')).toHaveTextContent(t('page.G6.loc.bothCoord'));
    await userEvent.type(lon, '200');
    await userEvent.click(submit);
    expect(within(form).getByRole('alert')).toHaveTextContent(t('page.G6.loc.badCoord'));
    // 서버: 영향 범위 없이 location_confirmed=true 는 422 — 좌표만으로는 보내지 않는다
    await userEvent.clear(lon);
    await userEvent.type(lon, '126.7');
    await userEvent.click(submit);
    expect(within(form).getByRole('alert')).toHaveTextContent(t('page.G6.loc.needTarget'));
    expect(matching(rec.requests, 'PATCH', /\/catalysts\//)).toHaveLength(0);
    rec.stop();
  });

  it('위치 확인된 호재 → "위치 확인 취소" → PATCH location_confirmed=false → 링크 지움 안내', async () => {
    server.use(
      http.patch(mswPath('/catalysts/:id'), async () => {
        const base = await example<CatalystUpdated>('/catalysts/42', 'PATCH');
        return HttpResponse.json({
          catalyst: { ...base.catalyst, id: 42, name: '검단구 신설', location_confirmed: false },
          links: [],
          job: null,
        } satisfies CatalystUpdated);
      }),
    );
    const rec = recordRequests();
    renderRoute('/market');
    const item = await row('검단구 신설');
    await userEvent.click(within(item).getByRole('button', { name: t('page.G6.loc.unconfirm') }));
    await waitFor(() => expect(matching(rec.requests, 'PATCH', '/catalysts/42')).toHaveLength(1));
    expect(await matching(rec.requests, 'PATCH', '/catalysts/42')[0]?.body).toEqual({
      location_confirmed: false,
    });
    expect(await within(await panel()).findByTestId('catalyst-links')).toHaveTextContent(
      t('page.G6.loc.cleared'),
    );
    rec.stop();
  });

  it('서버 422(영향 범위·지역 밖 단지) → 서버 detail 을 폼에 보인다', async () => {
    server.use(
      http.patch(mswPath('/catalysts/:id'), () =>
        HttpResponse.json(
          { code: 'validation_error', detail: '이 지역의 단지가 아니다: 999' },
          { status: 422 },
        ),
      ),
    );
    renderRoute('/market');
    const { form } = await openForm('GTX-B');
    await pickFirstComplex(form);
    await userEvent.click(within(form).getByRole('button', { name: t('page.G6.loc.submit') }));
    expect(await within(form).findByRole('alert')).toHaveTextContent('이 지역의 단지가 아니다');
  });
});
