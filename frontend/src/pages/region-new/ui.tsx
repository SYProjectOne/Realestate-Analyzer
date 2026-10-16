/** R11-SETUP(G0·G0-2·G8) 화면 공용 모양 조각 — 목업 RegionNew·LivingAreas·Reports 의 같은 모양 */

/** 목업 오류 줄(.err — 빨간 글자 · 옅은 빨간 바탕) */
export const ERROR_BOX =
  'rounded-[10px] border border-danger/30 bg-danger/5 px-3 py-2.5 text-sm text-danger';

export type StepState = 'done' | 'current' | 'todo';

/** 단계 번호 동그라미(목업 .stepn) */
export function StepNo({ n, state = 'current' }: { n: string; state?: StepState }) {
  const tone = state === 'todo' ? 'bg-chip text-muted' : 'bg-accent text-accent-fg';
  return (
    <span
      aria-hidden
      className={`inline-flex size-7 shrink-0 items-center justify-center rounded-full text-sm font-bold ${tone}`}
    >
      {n}
    </span>
  );
}
