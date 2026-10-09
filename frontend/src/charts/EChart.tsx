import { lazy, Suspense } from 'react';
import { t } from '@/i18n';
import { useInView } from '@/lib/useInView';
import type { EChartsOption } from './types';

// echarts 번들은 차트가 뷰포트에 처음 들어올 때 받는다(RA §7 "뷰포트 진입 시 lazy load").
// 전체 echarts 가 아니라 쓰는 계열·컴포넌트만 등록한 런타임(EChartRuntime) — 최대 청크 ≤ 500kB.
const ReactECharts = lazy(() => import('./EChartRuntime'));

export interface EChartProps {
  option: EChartsOption;
  height?: number;
  /** 스크린리더용 요약(차트 제목) */
  ariaLabel: string;
}

function Placeholder({ height }: { height: number }) {
  return (
    <div style={{ height }} className="flex items-center justify-center text-xs text-grayed">
      {t('chart.notRendered')}
    </div>
  );
}

/** ECharts 렌더러: IntersectionObserver로 보일 때만 마운트, SVG 렌더러(선명·다크 대응). */
export function EChart({ option, height = 280, ariaLabel }: EChartProps) {
  const [ref, inView] = useInView<HTMLDivElement>();
  return (
    <div ref={ref} role="img" aria-label={ariaLabel} style={{ height }} data-testid="echart">
      {inView ? (
        <Suspense fallback={<Placeholder height={height} />}>
          <ReactECharts
            option={option}
            style={{ height }}
            opts={{ renderer: 'svg' }}
            notMerge
            lazyUpdate
          />
        </Suspense>
      ) : (
        <Placeholder height={height} />
      )}
    </div>
  );
}
