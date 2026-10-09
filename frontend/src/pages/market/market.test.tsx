import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { ROLE_STORAGE_KEY, TOKEN_STORAGE_KEY } from '@/api/auth';
import { t } from '@/i18n';
import { resetMockState } from '@/mocks/handlers.extra';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { renderRoute } from '@/test/render';
import { matching, recordRequests } from '../_shared/testing';

vi.mock('echarts-for-react', () => ({ default: () => null }));
beforeEach(() => resetMockState());

describe('G6 지역 시장', () => {
  it('생활권 필터 → URL ?living_area= → GET /market?living_area=', async () => {
    const rec = recordRequests();
    const { router } = renderRoute('/market');
    await screen.findByText(t('chart.C03.title'));
    const select = screen.getByLabelText(t('page.G6.livingArea'));
    await waitFor(() => expect(select.querySelectorAll('option').length).toBeGreaterThan(1));
    const value = (select.querySelectorAll('option')[1] as HTMLOptionElement).value;
    await userEvent.selectOptions(select, value);
    await waitFor(() => expect(router.state.location.search).toContain(`living_area=${value}`));
    await waitFor(() =>
      expect(
        matching(rec.requests, 'GET', '/market').some(
          (r) => r.url.searchParams.get('living_area') === value,
        ),
      ).toBe(true),
    );
    rec.stop();
  });

  it('규제 요약 카드와 생활권별 실거래 시세 표', async () => {
    renderRoute('/market');
    expect(
      await screen.findByRole('heading', { name: t('page.G6.regulation') }),
    ).toBeInTheDocument();
    expect(screen.getByRole('table', { name: t('page.G6.prices') })).toBeInTheDocument();
  });
});

describe('M6 G6 호재 URL 입력', () => {
  async function form() {
    return screen.findByRole('form', { name: t('page.G6.catalyst.title') });
  }
  const URL_OK = 'https://www.example-news.kr/article/2026/10/08/12345';

  it('http(s)가 아닌 주소(javascript:·ftp:)는 막고 보내지 않는다', async () => {
    const rec = recordRequests();
    renderRoute('/market');
    const f = await form();
    for (const bad of ['javascript:alert(1)', 'ftp://example.com/a', 'example.com']) {
      const url = within(f).getByLabelText(t('page.G6.catalyst.url'));
      await userEvent.clear(url);
      await userEvent.type(url, bad);
      await userEvent.type(within(f).getByLabelText(t('page.G6.catalyst.titleField')), '제목');
      await userEvent.click(within(f).getByRole('button', { name: t('page.G6.catalyst.submit') }));
      expect(await within(f).findByRole('alert')).toHaveTextContent(t('page.G6.catalyst.badUrl'));
      await userEvent.clear(within(f).getByLabelText(t('page.G6.catalyst.titleField')));
    }
    expect(matching(rec.requests, 'POST', '/catalysts')).toHaveLength(0);
    rec.stop();
  });

  it('제목은 필수, 제목 200자·발췌 2000자 제한', async () => {
    const rec = recordRequests();
    renderRoute('/market');
    const f = await form();
    expect(within(f).getByLabelText(t('page.G6.catalyst.titleField'))).toHaveAttribute(
      'maxLength',
      '200',
    );
    expect(within(f).getByLabelText(t('page.G6.catalyst.excerpt'))).toHaveAttribute(
      'maxLength',
      '2000',
    );
    await userEvent.type(within(f).getByLabelText(t('page.G6.catalyst.url')), URL_OK);
    await userEvent.click(within(f).getByRole('button', { name: t('page.G6.catalyst.submit') }));
    expect(await within(f).findByRole('alert')).toHaveTextContent(
      t('page.G6.catalyst.titleRequired'),
    );
    expect(matching(rec.requests, 'POST', '/catalysts')).toHaveLength(0);
    rec.stop();
  });

  it('입력 → POST /catalysts {region_id,url,title,excerpt} → 성공 안내 + 분류 잡 진행', async () => {
    const rec = recordRequests();
    renderRoute('/market');
    const f = await form();
    await userEvent.type(within(f).getByLabelText(t('page.G6.catalyst.url')), URL_OK);
    await userEvent.type(
      within(f).getByLabelText(t('page.G6.catalyst.titleField')),
      '골드라인 연장 기본계획 승인',
    );
    await userEvent.type(within(f).getByLabelText(t('page.G6.catalyst.excerpt')), '발췌 문장');
    await userEvent.click(within(f).getByRole('button', { name: t('page.G6.catalyst.submit') }));
    await waitFor(() => expect(matching(rec.requests, 'POST', '/catalysts')).toHaveLength(1));
    const body = (await matching(rec.requests, 'POST', '/catalysts')[0]?.body) as Record<
      string,
      unknown
    >;
    expect(body).toEqual({
      region_id: expect.any(Number),
      url: URL_OK,
      title: '골드라인 연장 기본계획 승인',
      excerpt: '발췌 문장',
    });
    const done = await screen.findByTestId('catalyst-created');
    expect(done).toHaveTextContent(
      t('page.G6.catalyst.saved', { name: '골드라인 연장 기본계획 승인' }),
    );
    expect(await within(done).findByText('rejudge')).toBeInTheDocument();
    rec.stop();
  });

  it('job=null(스냅샷 없음) → 다음 파이프라인에서 분류한다는 안내', async () => {
    server.use(
      http.post(mswPath('/catalysts'), () =>
        HttpResponse.json(
          {
            catalyst: {
              id: 57,
              name: '새 호재',
              kind: '기타',
              stage: '미확정',
              stage_prob: { v: null, label: '확인 불가', reason: '분류 전', prov: null },
              decision: null,
              expected_ym: { v: null, label: '확인 불가', reason: '분류 전', prov: null },
              location_confirmed: false,
              linked_complex_ids: [],
            },
            job: null,
          },
          { status: 201 },
        ),
      ),
    );
    renderRoute('/market');
    const f = await form();
    await userEvent.type(within(f).getByLabelText(t('page.G6.catalyst.url')), URL_OK);
    await userEvent.type(within(f).getByLabelText(t('page.G6.catalyst.titleField')), '새 호재');
    await userEvent.click(within(f).getByRole('button', { name: t('page.G6.catalyst.submit') }));
    const done = await screen.findByTestId('catalyst-created');
    expect(done).toHaveTextContent(t('page.G6.catalyst.noJob'));
  });

  it('읽기 전용 토큰이면 입력·저장이 꺼진다', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-read');
    window.localStorage.setItem(ROLE_STORAGE_KEY, 'read');
    renderRoute('/market');
    const f = await form();
    expect(within(f).getByLabelText(t('page.G6.catalyst.url'))).toBeDisabled();
    const button = within(f).getByRole('button', { name: t('page.G6.catalyst.submit') });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute('title', t('auth.readOnlyHint'));
  });
});
