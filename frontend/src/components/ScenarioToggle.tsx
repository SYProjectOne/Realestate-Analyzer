import { useRef, type KeyboardEvent } from 'react';
import { t } from '@/i18n';

export interface ScenarioOption {
  /** 계약 Scenario.id는 숫자, URL 값은 문자열 — 둘 다 받고 onChange에는 문자열로 넘긴다 */
  id: string | number;
  name: string;
}

export interface ScenarioToggleProps {
  /** 내장 5개(기본·A·B·C·D) + 사용자 시나리오. 서버 Scenario[]를 {id,name}으로 넘긴다 */
  options: ScenarioOption[];
  /** 현재 선택 id (URL ?scenario=). null이면 첫 항목을 선택된 것으로 표시 */
  value: string | number | null;
  onChange: (id: string) => void;
  disabled?: boolean;
  /** radiogroup 접근성 이름 (기본 t('header.scenario')) */
  label?: string;
}

/** 상황 토글(세그먼트). 화살표 키로 이동. 전역 공유는 useScenario()가 한다. */
export function ScenarioToggle({
  options,
  value,
  onChange,
  disabled = false,
  label,
}: ScenarioToggleProps) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const first = options[0];
  const selected = value !== null ? String(value) : first ? String(first.id) : null;

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return;
    event.preventDefault();
    const step = event.key === 'ArrowRight' ? 1 : -1;
    const next = (index + step + options.length) % options.length;
    const option = options[next];
    if (option) {
      onChange(String(option.id));
      refs.current[next]?.focus();
    }
  };

  return (
    <div
      role="radiogroup"
      aria-label={label ?? t('header.scenario')}
      className="inline-flex overflow-hidden rounded-sm border border-border"
    >
      {options.map((option, index) => {
        const checked = String(option.id) === selected;
        return (
          <button
            key={option.id}
            ref={(el) => {
              refs.current[index] = el;
            }}
            type="button"
            role="radio"
            aria-checked={checked}
            tabIndex={checked ? 0 : -1}
            disabled={disabled}
            onClick={() => onChange(String(option.id))}
            onKeyDown={(event) => onKeyDown(event, index)}
            className={`px-2.5 py-1 text-sm ${
              checked ? 'bg-accent text-accent-fg' : 'bg-surface text-fg hover:bg-bg'
            } disabled:opacity-50`}
          >
            {option.name}
          </button>
        );
      })}
    </div>
  );
}
