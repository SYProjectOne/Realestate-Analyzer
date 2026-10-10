/**
 * R3 3차 minor 15: PATCH /claims 뒤(그리고 사람 확인 뒤) 사실을 보이는 화면 캐시가 무효화된다.
 * 강등(D10-3·D11-3)은 대시보드·리스트·상세·출처·체크리스트·보고서 차단 여부를 바꾼다.
 */
import { QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { createTestQueryClient } from '@/test/render';
import { resetMockState } from '@/mocks/handlers.extra';
import { useCreateHumanCheck, useReviseClaim } from './hooks';

beforeEach(() => resetMockState());

const FACT_KEYS = [
  ['snapshots', '12', 'dashboard', null],
  ['snapshots', '12', 'complexes', {}],
  ['snapshots', '12', 'compare', ['1', '2'], null],
  ['snapshots', '12', 'market', null],
  ['snapshots', '12', 'claims', { status: 'contradicted' }],
  ['complexes', '5', '12', null],
  ['provenance', 'fp_1'],
  ['ops', 'checklist', {}],
  ['reports', '12'],
] as const;
const UNRELATED = ['scenarios'] as const;

function setup() {
  const qc = createTestQueryClient();
  for (const key of [...FACT_KEYS, UNRELATED]) qc.setQueryData(key as readonly unknown[], { x: 1 });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { qc, wrapper };
}

const invalidated = (qc: ReturnType<typeof setup>['qc'], key: readonly unknown[]) =>
  qc.getQueryState(key)?.isInvalidated ?? false;

describe('사실 화면 캐시 무효화 (minor 15)', () => {
  it('PATCH /claims 성공 → 스냅샷 하위·단지 상세·출처·운영·보고서 무효화', async () => {
    const { qc, wrapper } = setup();
    const { result } = renderHook(() => useReviseClaim(), { wrapper });
    await act(async () => {
      await result.current.mutateAsync({ id: 6990, patch: { text: '고친 문장이다.' } });
    });
    await waitFor(() => {
      for (const key of FACT_KEYS) expect(invalidated(qc, key), JSON.stringify(key)).toBe(true);
    });
    expect(invalidated(qc, UNRELATED)).toBe(false);
  });

  it('사람 확인 저장 → 같은 범위 무효화(출처 패널 포함)', async () => {
    const { qc, wrapper } = setup();
    const { result } = renderHook(() => useCreateHumanCheck(), { wrapper });
    await act(async () => {
      await result.current.mutateAsync({
        complex_id: 5,
        field: 'intake_status',
        value_text: '접수 가능',
        kind: 'phone',
        // 계약 .11 F7: 시간대가 붙은 RFC3339(날짜만이면 422)
        checked_at: '2026-10-08T10:00:00+09:00',
        entered_by: '운영자',
      });
    });
    await waitFor(() => expect(invalidated(qc, ['provenance', 'fp_1'])).toBe(true));
    expect(invalidated(qc, ['complexes', '5', '12', null])).toBe(true);
  });

  it('사람 확인 201 + job_id(계약 .11 F6) → 지역·리비전 목록도 무효화(발행 대기 리비전 폴링 시작)', async () => {
    const { qc, wrapper } = setup();
    qc.setQueryData(['regions', '1', 'snapshots'], []);
    const { result } = renderHook(() => useCreateHumanCheck(), { wrapper });
    let jobId: number | null = null;
    await act(async () => {
      const hc = await result.current.mutateAsync({
        complex_id: 5,
        field: 'intake_status',
        value_text: '가능',
        kind: 'phone',
        checked_at: '2026-10-08T10:00:00Z',
        entered_by: '운영자',
      });
      jobId = hc.job_id ?? null;
    });
    expect(jobId).not.toBeNull();
    await waitFor(() => expect(invalidated(qc, ['regions', '1', 'snapshots'])).toBe(true));
  });
});
