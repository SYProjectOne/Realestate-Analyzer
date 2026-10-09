/**
 * D11-1 스냅샷 리비전(계약 .8 Snapshot.revision·revision_of·revision_reason): 같은 기준일의 리비전을 고를 수 있고, 기본 = 최신 published 리비전.
 */
import { screen, waitFor, within } from '@testing-library/react';
import { getResponse, http, HttpResponse, type RequestHandler } from 'msw';
import type { Snapshot } from '@/api/types';
import type { SnapshotLike } from '@/lib/contract';
import { t } from '@/i18n';
import { resetMockState } from '@/mocks/handlers.extra';
import { generatedHandlers } from '@/mocks/handlers.gen';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { renderRoute, renderWithProviders } from '@/test/render';
import { defaultSnapshot, SnapshotPicker, snapshotText, snapshotTitle } from './SnapshotPicker';

vi.mock('@/charts/EChartRuntime', () => ({ default: () => null }));
beforeEach(() => resetMockState());

const rev = (
  id: number,
  asof: string,
  revision: number,
  status = 'published',
  reason: string | null = null,
): SnapshotLike => ({ id, asof_date: asof, revision, status, revision_reason: reason });

describe('스냅샷 리비전 표시·기본 선택', () => {
  it('리비전 1(또는 필드 없음)은 날짜만, 2 이상은 "· 리비전 n" + 사유 툴팁', () => {
    expect(snapshotText({ id: 1, asof_date: '2026-10-08' })).toBe('2026-10-08');
    expect(snapshotText(rev(1, '2026-10-08', 1))).toBe('2026-10-08');
    expect(snapshotText(rev(2, '2026-10-08', 2, 'published', '사람 확인'))).toBe(
      t('picker.revision', { date: '2026-10-08', n: '2' }),
    );
    expect(snapshotTitle(rev(2, '2026-10-08', 2, 'published', '사람 확인'))).toBe(
      t('picker.revisionReason', { n: '2', reason: '사람 확인' }),
    );
    expect(snapshotTitle(rev(1, '2026-10-08', 1))).toBeUndefined();
    // 생성 중 리비전
    expect(snapshotText(rev(3, '2026-10-08', 3, 'building'))).toBe(
      t('picker.snapshotBuilding', {
        date: t('picker.revision', { date: '2026-10-08', n: '3' }),
      }),
    );
  });

  it('기본 = 최신 기준일의 최신 published 리비전(생성 중 리비전은 건너뛴다)', () => {
    const list = [
      rev(11, '2026-10-07', 1),
      rev(12, '2026-10-08', 1),
      rev(13, '2026-10-08', 2),
      rev(14, '2026-10-08', 3, 'building'),
    ];
    expect(defaultSnapshot(list)?.id).toBe(13);
    expect(defaultSnapshot([rev(14, '2026-10-08', 1, 'building')])?.id).toBe(14);
    expect(defaultSnapshot([])).toBeNull();
  });

  it('picker 옵션에 리비전이 따로 보인다', () => {
    renderWithProviders(
      <SnapshotPicker
        snapshots={[rev(13, '2026-10-08', 2, 'published', '생활권 편집'), rev(12, '2026-10-08', 1)]}
        value={13}
        onChange={() => {}}
      />,
    );
    const select = screen.getByLabelText(t('header.snapshot'));
    const options = within(select).getAllByRole('option');
    expect(options.map((o) => o.textContent)).toEqual([
      t('picker.revision', { date: '2026-10-08', n: '2' }),
      '2026-10-08',
    ]);
    expect(options[0]).toHaveAttribute(
      'title',
      t('picker.revisionReason', { n: '2', reason: '생활권 편집' }),
    );
    expect(select).toHaveValue('13');
  });

  it('헤더: 계약 응답에 같은 기준일 리비전 2(published)가 있으면 옵션에 보인다', async () => {
    // 계약 예시(snapshots_list.json, 리비전 1뿐)에 재판정 리비전 2 를 앞에 더한 응답
    server.use(
      http.get(mswPath('/regions/:id/snapshots'), async ({ request }) => {
        const res = await getResponse(generatedHandlers as RequestHandler[], request.clone());
        const list = (await res!.json()) as Snapshot[];
        const latest = list[0]!;
        const rev2: Snapshot = {
          ...latest,
          id: 99,
          revision: 2,
          revision_of: latest.id,
          revision_reason: '사람 확인 입력(재판정)',
          status: 'published',
        };
        return HttpResponse.json([rev2, ...list]);
      }),
    );
    renderRoute('/');
    const select = await screen.findByLabelText(t('header.snapshot'));
    expect(
      await within(select).findByRole('option', {
        name: new RegExp(t('picker.revision', { date: '2026-10-08', n: '2' })),
      }),
    ).toBeInTheDocument();
  });

  it('헤더: 계약 예시(리비전 1뿐)면 옵션은 기준일만, 기본 = 최신 published', async () => {
    renderRoute('/');
    const select = await screen.findByLabelText(t('header.snapshot'));
    await waitFor(() => expect(within(select).getAllByRole('option').length).toBeGreaterThan(1));
    const texts = within(select)
      .getAllByRole('option')
      .map((o) => o.textContent);
    expect(texts[0]).toBe('2026-10-08');
    await waitFor(() => expect(select).toHaveValue('12'));
  });
});
