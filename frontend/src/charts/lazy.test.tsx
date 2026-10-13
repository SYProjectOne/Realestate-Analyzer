/**
 * R5-FE 2(D25-1): RA §7 공통 규칙 "차트는 뷰포트 진입 시 lazy load".
 * 화면 밖 차트는 플레이스홀더(SVG 없음, echarts 런타임 미마운트)였다가 IntersectionObserver 가 진입을 알리면 그려진다.
 * 실제 브라우저 스크롤은 e2e/pages/pages.spec.ts "차트 지연 로딩" 이 본다.
 */
import { act, render, screen, waitFor } from '@testing-library/react';
import { t } from '@/i18n';
import { EChart } from './EChart';

const runtimeMounts = vi.hoisted(() => ({ n: 0 }));

// echarts 런타임 대신 SVG 하나를 그리는 가짜 — 마운트 횟수를 센다
vi.mock('./EChartRuntime', () => ({
  default: () => {
    runtimeMounts.n += 1;
    return <svg data-testid="echart-svg" />;
  },
}));

type Callback = (entries: Pick<IntersectionObserverEntry, 'isIntersecting' | 'target'>[]) => void;

/** 관찰 대상·옵션을 기록하고, 테스트가 진입/이탈을 직접 알린다 */
class FakeObserver {
  static all: FakeObserver[] = [];
  readonly targets: Element[] = [];
  disconnected = false;
  constructor(
    readonly callback: Callback,
    readonly options: IntersectionObserverInit = {},
  ) {
    FakeObserver.all.push(this);
  }
  observe(target: Element): void {
    this.targets.push(target);
  }
  unobserve(): void {}
  disconnect(): void {
    this.disconnected = true;
  }
  takeRecords(): IntersectionObserverEntry[] {
    return [];
  }
  fire(isIntersecting: boolean): void {
    act(() => this.callback(this.targets.map((target) => ({ isIntersecting, target }))));
  }
}

function observerOf(el: Element): FakeObserver {
  const found = FakeObserver.all.find((o) => o.targets.includes(el) && !o.disconnected);
  if (!found) throw new Error('관찰 중인 IntersectionObserver 가 없다');
  return found;
}

beforeEach(() => {
  FakeObserver.all = [];
  runtimeMounts.n = 0;
  vi.stubGlobal('IntersectionObserver', FakeObserver);
});
afterEach(() => vi.unstubAllGlobals());

const option = { series: [] };

describe('차트 지연 로딩(뷰포트 진입 시)', () => {
  it('화면 밖: 플레이스홀더만 있고 SVG·echarts 런타임이 없다 → 진입하면 그린다', async () => {
    render(<EChart option={option} ariaLabel="c-below" height={200} />);
    const box = screen.getByRole('img', { name: 'c-below' });
    // 플레이스홀더: 자리(높이)는 잡혀 있고 SVG 는 없다
    expect(box).toHaveStyle({ height: '200px' });
    expect(box).toHaveTextContent(t('chart.notRendered'));
    expect(box.querySelector('svg')).toBeNull();
    expect(runtimeMounts.n).toBe(0);

    const observer = observerOf(box);
    // 미리 받기 여백(rootMargin)이 있다 — 스크롤이 닿기 조금 전에 시작
    expect(observer.options.rootMargin).toBeTruthy();

    // 아직 밖(isIntersecting=false) → 그대로
    observer.fire(false);
    expect(box.querySelector('svg')).toBeNull();
    expect(runtimeMounts.n).toBe(0);

    // 스크롤로 들어옴 → 런타임 마운트·SVG, 관찰 종료
    observer.fire(true);
    await waitFor(() => expect(box.querySelector('svg')).not.toBeNull());
    expect(box).not.toHaveTextContent(t('chart.notRendered'));
    expect(runtimeMounts.n).toBeGreaterThan(0);
    expect(observer.disconnected).toBe(true);
  });

  it('여러 차트는 각자 진입할 때만 그린다(한 번 그리면 유지)', async () => {
    render(
      <>
        <EChart option={option} ariaLabel="c-top" />
        <EChart option={option} ariaLabel="c-bottom" />
      </>,
    );
    const top = screen.getByRole('img', { name: 'c-top' });
    const bottom = screen.getByRole('img', { name: 'c-bottom' });
    observerOf(top).fire(true);
    await waitFor(() => expect(top.querySelector('svg')).not.toBeNull());
    expect(bottom.querySelector('svg')).toBeNull();
    expect(bottom).toHaveTextContent(t('chart.notRendered'));

    const bottomObserver = observerOf(bottom);
    bottomObserver.fire(true);
    await waitFor(() => expect(bottom.querySelector('svg')).not.toBeNull());
    // 다시 나가도(관찰 끝) 지우지 않는다
    expect(bottomObserver.disconnected).toBe(true);
    expect(top.querySelector('svg')).not.toBeNull();
  });
});
