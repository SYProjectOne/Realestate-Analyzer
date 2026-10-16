/**
 * R11-SETUP(D30, 목업 Reports): G8 '만들기 4단계 → 막힌 이유(고칠 곳 링크) → 만든 보고서 → 바뀐 항목' 모양과 문구.
 * 지금 동작(생성·오류 409/422/503·Bearer 다운로드·비교는 앞선 리비전만)은 reports.test.tsx · r3d~r3i2 가 지킨다.
 */
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { getResponse, http, HttpResponse, type RequestHandler } from 'msw';
import { TOKEN_STORAGE_KEY } from '@/api/auth';
import type { ChangeEvent, Report, Snapshot } from '@/api/types';
import { t } from '@/i18n';
import { generatedHandlers } from '@/mocks/handlers.gen';
import { resetMockState } from '@/mocks/handlers.extra';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { renderRoute } from '@/test/render';

vi.mock('@/charts/EChartRuntime', () => ({ default: () => null }));
beforeEach(() => resetMockState());

async function example<T>(path: string): Promise<T> {
  const res = await getResponse(
    generatedHandlers as RequestHandler[],
    new Request(`http://localhost/api${path}`),
  );
  return (await res?.json()) as T;
}

async function ready() {
  window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-write');
  renderRoute('/reports');
  const button = await screen.findByRole('button', { name: t('page.G8.generate') });
  await waitFor(() => expect(button).toBeEnabled());
  return button;
}

describe('R11 G8 보고서 — 목업 Reports', () => {
  it('머리: 지역 · 발행된 기준일 수 · 만든 보고서 수(목록 세기) + 질문형 h1 + 소개', async () => {
    await ready();
    const snapshots = await example<Snapshot[]>('/regions/1/snapshots');
    const reports = await example<Report[]>('/reports');
    const published = snapshots.filter((s) => s.status === 'published').length;
    await waitFor(() =>
      expect(
        screen.getByText(
          (_, el) =>
            el?.getAttribute('data-meta') === 'count' &&
            (el.textContent ?? '').includes(
              t('page.G8.summary', {
                region: '',
                snapshots: String(published),
                reports: String(reports.length),
              }).slice(3),
            ),
        ),
      ).toBeInTheDocument(),
    );
    expect(screen.getByRole('heading', { level: 1, name: t('page.G8.title') })).toBeVisible();
    expect(screen.getByText(t('page.G8.intro'))).toBeInTheDocument();
  });

  it('만들기 4단계: 질문형 라벨 · 설명(?) · 선택 요약 · 만들 수 있어요(남은 모순 주장 0건) · 진행 자리표시', async () => {
    await ready();
    expect(screen.getByRole('heading', { level: 2, name: t('page.G8.createTitle') })).toBeVisible();
    expect(screen.getByLabelText(t('page.G8.snapshot'))).toBeInTheDocument();
    expect(screen.getByLabelText(t('page.G8.compareSnapshot'))).toBeInTheDocument();
    expect(screen.getByLabelText(t('page.G8.scenario'))).toBeInTheDocument();
    expect(screen.getByRole('group', { name: t('page.G8.format') })).toBeInTheDocument();
    // 형식 라디오: 이름은 형식만, 설명은 aria-describedby
    const pdf = screen.getByRole('radio', { name: t('page.G8.formats.pdf') });
    expect(pdf).toHaveAccessibleDescription(t('page.G8.formatHint.pdf'));
    await userEvent.click(screen.getByRole('button', { name: t('page.G8.snapshotHelp') }));
    expect(screen.getByRole('note')).toHaveTextContent(t('page.G8.snapshotHelpBody'));
    expect(screen.getByTestId('g8-ready')).toHaveTextContent(t('page.G8.ready', { n: '0' }));
    const selection = screen.getByTestId('g8-selection');
    expect(selection).toHaveTextContent(t('page.G8.scenarioDefault'));
    expect(selection).toHaveTextContent(t('page.G8.formats.html'));
    await userEvent.click(pdf);
    expect(selection).toHaveTextContent(t('page.G8.formats.pdf'));
    expect(screen.getByTestId('g8-progress-slot')).toHaveTextContent(t('page.G8.progressSlot'));
  });

  it('모순 주장이 남으면: 막힌 이유(role=alert, 버튼이 가리킴) + 데이터·운영 화면으로 고치러 가는 링크, "만들 수 있어요" 없음', async () => {
    const snapshots = await example<Snapshot[]>('/regions/1/snapshots');
    server.use(
      http.get(mswPath('/regions/:id/snapshots'), () =>
        HttpResponse.json(
          snapshots.map((s, i) => (i === 0 ? { ...s, contradicted_claims: 3 } : s)),
        ),
      ),
    );
    renderRoute('/reports');
    const button = await screen.findByRole('button', { name: t('page.G8.generate') });
    const reason = await screen.findByText(t('page.G8.blocked', { n: '3' }));
    expect(reason).toHaveAttribute('role', 'alert');
    expect(button).toHaveAttribute('aria-describedby', reason.id);
    const fix = within(reason).getByRole('link', { name: t('page.G8.blockedFix') });
    expect(fix.getAttribute('href')).toMatch(/^\/ops/);
    expect(screen.queryByTestId('g8-ready')).toBeNull();
  });

  it('409 publish_blocked 도 고칠 곳 링크를 붙이고, 만들기를 누르면 진행 자리표시가 작업 진행으로 바뀐다', async () => {
    server.use(
      http.post(mswPath('/reports'), () =>
        HttpResponse.json(
          { code: 'publish_blocked', detail: '남은 모순 주장 1건' },
          { status: 409 },
        ),
      ),
    );
    const button = await ready();
    await userEvent.click(button);
    const msg = await screen.findByText(t('page.G8.conflict', { detail: '남은 모순 주장 1건' }));
    expect(within(msg).getByRole('link', { name: t('page.G8.blockedFix') })).toBeInTheDocument();
    expect(screen.getByTestId('g8-progress-slot')).toBeInTheDocument();
  });

  it('만든 보고서: 쉬운 열 이름 · 상태 알약(data-status) · 비교 없음은 "—" · 파일 이름 버튼', async () => {
    await ready();
    const table = await screen.findByRole('table', { name: t('page.G8.list') });
    const heads = within(table)
      .getAllByRole('columnheader')
      .map((h) => h.textContent);
    expect(heads).toEqual(
      (['created', 'snapshot', 'compare', 'format', 'status', 'size', 'file'] as const).map((k) =>
        t(`page.G8.col.${k}`),
      ),
    );
    const reports = await example<Report[]>('/reports');
    for (const r of reports) {
      expect(table.querySelector(`[data-status="${r.status}"]`)).not.toBeNull();
    }
    if (reports.some((r) => r.compare_snapshot_id === null)) {
      expect(within(table).getAllByText('—').length).toBeGreaterThan(0);
    }
    const region = screen.getByRole('region', { name: t('page.G8.list') });
    expect(region).toHaveTextContent(t('page.G8.listWhat'));
  });

  it('바뀐 항목: 비교 쌍 알약 · 요약 칸 4개(행 세기) · 단지 이름 = 상세 링크 · 해시 값은 접어 두고 풀이', async () => {
    await ready();
    const compare = screen.getByLabelText(t('page.G8.compareSnapshot'));
    const value = (compare.querySelectorAll('option')[1] as HTMLOptionElement).value;
    await userEvent.selectOptions(compare, value);
    const table = await screen.findByRole('table', { name: t('page.G8.diff') });
    const rows: ChangeEvent[] = (await example<ChangeEvent[]>(`/snapshots/12/changes`)) ?? [];
    expect(screen.getByTestId('g8-diff-pair')).toBeInTheDocument();
    const summary = screen.getByTestId('g8-diff-summary');
    const shown = within(table).getAllByRole('row').length - 1;
    expect(summary).toHaveTextContent(t('page.G8.tile.countValue', { n: String(shown) }));
    expect(summary).toHaveTextContent(t('page.G8.tile.critical'));
    const linked = rows.find((r) => r.complex_id && r.complex_name);
    if (linked) {
      const link = within(table).getAllByRole('link', { name: linked.complex_name! })[0];
      expect(link?.getAttribute('href')).toMatch(new RegExp(`^/complexes/${linked.complex_id}`));
    }
    const hashed = rows.find((r) => r.value_kind === 'hash' && r.summary);
    if (hashed) {
      const summaryEl = within(table).getAllByText(hashed.summary!)[0] as HTMLElement;
      const details = summaryEl.closest('details') as HTMLElement;
      expect(details).not.toHaveAttribute('open');
      expect(within(details).getByText(t('page.G8.hashNote'))).toBeInTheDocument();
    }
  });

  it('바닥: 보고서는 자격을 판정하지 않는다는 고지 + 라벨 범례', async () => {
    await ready();
    expect(screen.getByText(t('page.G8.footnote'))).toBeInTheDocument();
    expect(screen.getAllByTestId('provenance-legend').length).toBeGreaterThan(0);
  });
});
