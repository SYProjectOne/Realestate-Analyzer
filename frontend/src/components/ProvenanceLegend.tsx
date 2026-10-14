import { useId, useState } from 'react';
import { t, type TKey } from '@/i18n';

const HELP_KEYS: readonly TKey[] = [
  'label.help.confirmed',
  'label.help.estimated',
  'label.help.unofficial',
  'label.help.reprocessed',
  'label.help.unknown',
  'label.help.human',
];

/**
 * 출처 범례 한 줄(P3, 30-proposal §4): "밑줄 친 숫자를 누르면 출처·확인일이 열립니다 · 라벨 뜻 ⓘ".
 * 'ⓘ 라벨 뜻'은 펼침(aria-expanded) — 라벨 6가지 정의. Esc 로 닫는다. 정보를 더하기만 한다.
 */
export function ProvenanceLegend({ className = '' }: { className?: string }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <div
      className={`flex flex-col gap-1 text-xs text-muted ${className}`}
      data-testid="provenance-legend"
      onKeyDown={(event) => {
        if (event.key === 'Escape' && open) {
          event.stopPropagation();
          setOpen(false);
        }
      }}
    >
      <p className="flex flex-wrap items-center gap-x-1">
        <span>{t('label.legend')}</span>
        <span aria-hidden>·</span>
        <button
          type="button"
          aria-expanded={open}
          aria-controls={id}
          onClick={() => setOpen((v) => !v)}
          className="inline-flex items-center gap-0.5 rounded-sm underline decoration-dotted underline-offset-2 hover:text-fg focus:outline-hidden focus-visible:ring-2 focus-visible:ring-accent"
        >
          {t('label.legendHelp')}
          <span aria-hidden>ⓘ</span>
        </button>
      </p>
      {open ? (
        <ul
          id={id}
          aria-label={t('label.legendHelp')}
          className="flex flex-col gap-0.5 rounded-sm border border-border bg-surface p-2 text-fg"
        >
          {HELP_KEYS.map((key) => (
            <li key={key}>{t(key)}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
