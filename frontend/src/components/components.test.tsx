import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type {
  IntakeLike as Intake,
  RegionLike as Region,
  SnapshotLike as Snapshot,
} from '@/lib/contract';
import { renderWithProviders } from '@/test/render';
import {
  CachedBadge,
  DataTableToggle,
  EmptyState,
  IntakeBadge,
  JobProgressView,
  LabelBadge,
  MismatchBadge,
  RegionPicker,
  ScenarioToggle,
  SnapshotPicker,
  TieBadge,
  UnstableBadge,
} from './index';

describe('배지', () => {
  it('LabelBadge: 텍스트 배지 + 확인 불가(사유)', () => {
    renderWithProviders(
      <>
        <LabelBadge label="비공식" />
        <LabelBadge label="확인 불가" reason="스캔" />
      </>,
    );
    expect(screen.getByText('비공식')).toBeInTheDocument();
    expect(screen.getByText('확인 불가(스캔)')).toBeInTheDocument();
  });

  it('IntakeBadge: 상태 · 경로, 없으면 확인 불가', () => {
    const intake: Intake = {
      status: '가능',
      path: 'human_check',
      evidence_url: null,
      checked_at: '2026-10-08',
      http_status: null,
    };
    renderWithProviders(
      <>
        <IntakeBadge intake={intake} />
        <IntakeBadge intake={null} />
      </>,
    );
    expect(screen.getByText('접수 가능 · 사람 확인')).toBeInTheDocument();
    expect(screen.getByText('접수 상태 확인 불가')).toBeInTheDocument();
  });

  it('Cached/Tie/Mismatch/Unstable: 참일 때만 렌더', () => {
    const { container } = renderWithProviders(
      <>
        <CachedBadge cached={false} />
        <TieBadge tie={false} />
        <MismatchBadge mismatch={false} />
        <UnstableBadge unstable={false} />
      </>,
    );
    expect(container).toBeEmptyDOMElement();
    renderWithProviders(
      <>
        <CachedBadge cached />
        <TieBadge tie confidence={0.48} />
        <MismatchBadge mismatch />
        <UnstableBadge unstable />
      </>,
    );
    expect(screen.getByText('캐시')).toBeInTheDocument();
    expect(screen.getByText('동률(신뢰도 0.48)')).toBeInTheDocument();
    expect(screen.getByText('증거와 상이')).toBeInTheDocument();
    expect(screen.getByText('순위 불안정')).toBeInTheDocument();
  });

  it('EmptyState: 확인 불가(사유)', () => {
    renderWithProviders(<EmptyState reason="403" />);
    expect(screen.getByRole('status')).toHaveTextContent('확인 불가(403)');
  });
});

describe('선택기', () => {
  it('ScenarioToggle: 클릭·화살표 키로 onChange', async () => {
    const onChange = vi.fn();
    renderWithProviders(
      <ScenarioToggle
        options={[
          { id: 'a', name: '기본' },
          { id: 'b', name: 'B' },
        ]}
        value="a"
        onChange={onChange}
      />,
    );
    await userEvent.click(screen.getByRole('radio', { name: 'B' }));
    expect(onChange).toHaveBeenLastCalledWith('b');
    screen.getByRole('radio', { name: '기본' }).focus();
    await userEvent.keyboard('{ArrowRight}');
    expect(onChange).toHaveBeenLastCalledWith('b');
  });

  it('RegionPicker: "지역 추가" 선택 → onAddRegion', async () => {
    const onAdd = vi.fn();
    const region = { id: 'rg_1', name: '픽스처 지역' } as Region;
    renderWithProviders(
      <RegionPicker regions={[region]} value="rg_1" onChange={() => {}} onAddRegion={onAdd} />,
    );
    await userEvent.selectOptions(screen.getByLabelText('지역'), '+ 지역 추가');
    expect(onAdd).toHaveBeenCalled();
  });

  it('SnapshotPicker: 선택 → onChange(id)', async () => {
    const onChange = vi.fn();
    const snapshots = [
      { id: 's2', asof_date: '2026-10-08' },
      { id: 's1', asof_date: '2026-10-07' },
    ] as Snapshot[];
    renderWithProviders(<SnapshotPicker snapshots={snapshots} value="s2" onChange={onChange} />);
    await userEvent.selectOptions(screen.getByLabelText('기준일'), 's1');
    expect(onChange).toHaveBeenCalledWith('s1');
  });
});

describe('DataTableToggle · JobProgressView', () => {
  it('"표로 보기"로 열면 Fact·숫자·빈 값을 포맷해 보여 준다', async () => {
    renderWithProviders(
      <DataTableToggle
        caption="테스트"
        table={{
          columns: [
            { key: 'name', header: '이름' },
            { key: 'price', header: '가격', unit: 'won' },
            { key: 'n', header: '세대', unit: 'households' },
          ],
          rows: [
            {
              name: '가',
              price: { v: 35_000_000, label: '추정', prov: null, checked_at: null },
              n: 1200,
            },
            { name: '나', price: null, n: null },
          ],
        }}
      />,
    );
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '표로 보기' }));
    expect(screen.getByRole('table')).toBeInTheDocument();
    expect(screen.getByText('3,500만원')).toBeInTheDocument();
    expect(screen.getByText('1,200세대')).toBeInTheDocument();
    expect(screen.getAllByText('확인 불가').length).toBe(2);
  });

  it('JobProgressView: 상태 텍스트', () => {
    renderWithProviders(
      <JobProgressView
        job={{
          id: 'j',
          job_name: 'rejudge',
          status: 'running',
          error_text: null,
        }}
      />,
    );
    expect(screen.getByRole('status')).toHaveTextContent('실행 중');
  });
});
