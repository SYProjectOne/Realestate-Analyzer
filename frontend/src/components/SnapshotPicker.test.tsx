/**
 * D11-1 스냅샷 리비전(계약 .8 초안): 같은 기준일의 리비전을 고를 수 있고, 기본 = 최신 published 리비전.
 */
import { screen, within } from '@testing-library/react';
import type { SnapshotLike } from '@/lib/contract';
import { t } from '@/i18n';
import { MOCK_REVISIONS_KEY, resetMockState } from '@/mocks/handlers.extra';
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

  it('헤더 기준일 선택에 리비전 2 가 보인다(MSW 초안 응답)', async () => {
    window.localStorage.setItem(MOCK_REVISIONS_KEY, '1');
    renderRoute('/');
    const select = await screen.findByLabelText(t('header.snapshot'));
    expect(
      await within(select).findByRole('option', {
        name: new RegExp(t('picker.revision', { date: '2026-10-08', n: '2' })),
      }),
    ).toBeInTheDocument();
  });
});
