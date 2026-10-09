import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { FactLike as Fact } from '@/lib/contract';
import { FactCell } from './FactCell';

const fact = (overrides: Partial<Fact> = {}): Fact => ({
  v: 749_000_000,
  label: '추정',
  prov: 'fp_01',
  checked_at: '2026-10-08',
  ...overrides,
});

describe('FactCell', () => {
  it('포맷한 값과 라벨 배지(텍스트)를 함께 렌더한다', () => {
    render(<FactCell fact={fact()} unit="won" onOpenProvenance={() => {}} />);
    expect(screen.getByText('7억 4,900만원')).toBeInTheDocument();
    expect(screen.getByText('추정')).toBeInTheDocument();
  });

  it('클릭하면 onOpenProvenance(prov)를 부른다', async () => {
    const onOpen = vi.fn();
    render(<FactCell fact={fact()} unit="won" onOpenProvenance={onOpen} />);
    await userEvent.click(screen.getByRole('button'));
    expect(onOpen).toHaveBeenCalledWith('fp_01');
  });

  it('prov가 없으면 버튼이 아니다', () => {
    render(<FactCell fact={fact({ prov: null })} unit="won" onOpenProvenance={() => {}} />);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('값이 없으면 "확인 불가(사유, 확인일)" 한 번만(계약 fact.json 표시 규칙 1)', () => {
    render(<FactCell fact={fact({ v: null, label: '확인 불가', reason: '스캔' })} unit="won" />);
    expect(screen.getAllByText('확인 불가(스캔, 2026-10-08)')).toHaveLength(1);
  });

  it('확인일이 없으면 "확인 불가(사유)"', () => {
    render(
      <FactCell
        fact={fact({ v: null, label: '확인 불가', reason: '스캔', checked_at: null })}
        unit="won"
      />,
    );
    expect(screen.getByText('확인 불가(스캔)')).toBeInTheDocument();
  });

  it('다른 라벨의 사유는 "<라벨>(<사유>)" 배지', () => {
    render(<FactCell fact={fact({ reason: '대체·보정 c=0.015' })} unit="won" />);
    expect(screen.getByText('추정(대체·보정 c=0.015)')).toBeInTheDocument();
  });

  it('fact 자체가 없으면 emptyReason으로 "확인 불가(사유)"', () => {
    render(<FactCell fact={null} unit="won" emptyReason="출처 누락" />);
    expect(screen.getByText('확인 불가(출처 누락)')).toBeInTheDocument();
  });

  it('사람 확인 값은 "사람 확인됨" 배지', () => {
    render(<FactCell fact={fact({ label: '확인됨', human: true })} unit="won" />);
    expect(screen.getByText('사람 확인됨')).toBeInTheDocument();
  });

  it('날짜는 기준일 대비 D±를 함께 보여 준다', () => {
    render(
      <FactCell fact={fact({ v: '2026-10-11', label: '확인됨' })} unit="date" asof="2026-10-08" />,
    );
    expect(screen.getByText('2026-10-11 (D-3)')).toBeInTheDocument();
  });

  it('showLabel=false면 배지를 숨긴다', () => {
    render(<FactCell fact={fact()} unit="won" showLabel={false} />);
    expect(screen.queryByText('추정')).not.toBeInTheDocument();
  });
});
