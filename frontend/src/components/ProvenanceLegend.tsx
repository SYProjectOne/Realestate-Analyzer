import { useId, useState } from 'react';
import { t, type TKey } from '@/i18n';
import type { Label } from '@/lib/contract';
import { LabelBadge } from './LabelBadge';

/**
 * 라벨 뜻 여섯 줄(SH-1·GL-1): 라벨 이름 + `label.help.*` 한 문장. 용어 사전 '라벨' 카드와 같은 원본을 쓴다.
 * human = '사람 확인됨'(라벨이 아니라 접두어, RA §3).
 */
export const LABEL_HELP: readonly {
  key: 'confirmed' | 'estimated' | 'unofficial' | 'reprocessed' | 'unknown' | 'human';
  label: Label;
  human?: boolean;
  text: TKey;
}[] = [
  { key: 'confirmed', label: '확인됨', text: 'label.help.confirmed' },
  { key: 'estimated', label: '추정', text: 'label.help.estimated' },
  { key: 'unofficial', label: '비공식', text: 'label.help.unofficial' },
  { key: 'reprocessed', label: '재가공', text: 'label.help.reprocessed' },
  { key: 'unknown', label: '확인 불가', text: 'label.help.unknown' },
  { key: 'human', label: '확인됨', human: true, text: 'label.help.human' },
];

/**
 * 출처 범례 한 줄(P3, 30-proposal §4 · 목업 §3): "밑줄 점선이 있는 숫자를 누르면 출처·확인한 날이 열려요 · 라벨 뜻 ⓘ".
 * '라벨 뜻'은 펼침(aria-expanded) — 라벨 6가지 이름(배지 모양 그대로) + 뜻. Esc 로 닫는다. 정보를 더하기만 한다.
 */
export function ProvenanceLegend({ className = '' }: { className?: string }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <div
      className={`flex flex-col gap-1.5 text-xs text-muted ${className}`}
      data-testid="provenance-legend"
      onKeyDown={(event) => {
        if (event.key === 'Escape' && open) {
          event.stopPropagation();
          setOpen(false);
        }
      }}
    >
      <p className="flex flex-wrap items-center gap-x-1.5">
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
          className="flex flex-col gap-1 rounded-xl border border-border bg-surface p-3 text-[13px] leading-relaxed text-fg-2"
        >
          {LABEL_HELP.map((item) => (
            <li key={item.key} className="flex flex-wrap items-baseline gap-x-2">
              <LabelBadge label={item.label} human={item.human} />
              <span>{t(item.text)}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
