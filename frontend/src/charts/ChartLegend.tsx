import { useId } from 'react';
import { t } from '@/i18n';
import type { ChartLegendItem, ChartLegendSymbol } from './types';

/** 빗금 기호 — pattern id 는 범례마다 고유(useId) */
function HatchSymbol({ color }: { color: string }) {
  const id = `chart-hatch-${useId().replace(/:/g, '')}`;
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden>
      <defs>
        <pattern id={id} width="4" height="4" patternUnits="userSpaceOnUse">
          <path d="M0 4 4 0" stroke={color} strokeWidth="1.5" />
        </pattern>
      </defs>
      <rect x="1.5" y="1.5" width="11" height="11" rx="2" fill={`url(#${id})`} stroke={color} />
    </svg>
  );
}

/** 범례 기호(14×14 SVG). 모양이 계열을 함께 구분한다(색각 이상·흑백 인쇄) */
function LegendSymbol({ symbol, color }: { symbol: ChartLegendSymbol; color: string }) {
  const common = { width: 14, height: 14, viewBox: '0 0 14 14', 'aria-hidden': true } as const;
  switch (symbol) {
    case 'circle':
      return (
        <svg {...common}>
          <circle cx="7" cy="7" r="5" fill={color} />
        </svg>
      );
    case 'ring':
      return (
        <svg {...common}>
          <circle cx="7" cy="7" r="4.5" fill="none" stroke={color} strokeWidth="2" />
        </svg>
      );
    case 'dashedRing':
      return (
        <svg {...common}>
          <circle
            cx="7"
            cy="7"
            r="4.5"
            fill="none"
            stroke={color}
            strokeWidth="1.5"
            strokeDasharray="2 1.5"
          />
        </svg>
      );
    case 'rect':
      return (
        <svg {...common}>
          <rect x="2" y="2" width="10" height="10" fill={color} />
        </svg>
      );
    case 'triangle':
      return (
        <svg {...common}>
          <path d="M7 1.5 12.5 12H1.5z" fill={color} />
        </svg>
      );
    case 'triangleDown':
      return (
        <svg {...common}>
          <path d="M1.5 2h11L7 12.5z" fill={color} />
        </svg>
      );
    case 'diamond':
      return (
        <svg {...common}>
          <path d="M7 1 13 7 7 13 1 7z" fill={color} />
        </svg>
      );
    case 'pin':
      return (
        <svg {...common}>
          <path d="M7 13s4.5-4.6 4.5-8a4.5 4.5 0 1 0-9 0c0 3.4 4.5 8 4.5 8z" fill={color} />
        </svg>
      );
    case 'line':
      return (
        <svg width="22" height="14" viewBox="0 0 22 14" aria-hidden>
          <line x1="0" y1="7" x2="22" y2="7" stroke={color} strokeWidth="2.5" />
          <circle cx="11" cy="7" r="3" fill={color} />
        </svg>
      );
    case 'dashedLine':
      return (
        <svg width="22" height="14" viewBox="0 0 22 14" aria-hidden>
          <line x1="0" y1="7" x2="22" y2="7" stroke={color} strokeWidth="2" strokeDasharray="4 3" />
          <rect x="8" y="4" width="6" height="6" fill={color} />
        </svg>
      );
    case 'range':
      return (
        <svg width="22" height="14" viewBox="0 0 22 14" aria-hidden>
          <rect x="1" y="5" width="20" height="4" rx="2" fill={color} />
        </svg>
      );
    case 'tick':
      return (
        <svg {...common}>
          <rect x="6" y="1" width="2" height="12" fill={color} />
        </svg>
      );
    case 'hatch':
      return <HatchSymbol color={color} />;
    case 'square':
    default:
      return (
        <svg {...common}>
          <rect x="1" y="1" width="12" height="12" rx="3" fill={color} />
        </svg>
      );
  }
}

/**
 * 차트 위 범례(HTML) — 줄바꿈되므로 축 라벨·막대와 겹치지 않는다(C04 겹침 결함). 글자는 글자색 토큰,
 * 색 기호는 옆에만(데이터 색으로 글자를 칠하지 않는다).
 */
export function ChartLegend({ items }: { items: readonly ChartLegendItem[] }) {
  if (items.length === 0) return null;
  return (
    <ul
      aria-label={t('chart.legend')}
      data-testid="chart-legend"
      className="m-0 flex list-none flex-wrap gap-x-4 gap-y-1 p-0 text-xs text-fg"
    >
      {items.map((item) => (
        <li key={`${item.symbol}-${item.name}`} className="inline-flex items-center gap-1.5">
          <LegendSymbol symbol={item.symbol} color={item.color} />
          <span>{item.name}</span>
          {item.note ? <span className="text-muted">{item.note}</span> : null}
        </li>
      ))}
    </ul>
  );
}
