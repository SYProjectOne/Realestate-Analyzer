import { useState } from 'react';
import { Link } from 'react-router';
import type { ChangeEvent } from '@/api/types';
import { Card, EmptyState, MetaText, StatusPill } from '@/components';
import { t } from '@/i18n';
import { formatDate } from '@/lib/format';
import {
  changeEntityText,
  changeFieldText,
  changeValueText,
  enumText,
  useGlobalSearch,
} from '../_shared';
import { Collapsible } from './RegionMarket';

/** 처음 보이는 변경 수 — 나머지는 '변경 n건 더 보기'(1클릭) */
export const CHANGES_SHOWN = 3;

/**
 * '최근에 바뀐 것'(Main 보드 · 고침 HM-14, D25-2: 변경 기록이지 사실이 아니다). 한 줄 = 중요도 · 다시 판정해요 · 단지(또는
 * 대상 이름) · 서버 요약 한 줄(title = 필드 이름) · 감지일. hash·json 값은 '바뀐 값 보기' 펼침, 짧은 값은 이전 → 이후 바로.
 * 지역 첫 적재(first_load)는 요약 문장 그대로. 줄을 누르면 단지 상세의 해당 탭(#tab).
 */
export function ChangeFeed({ changes, asof }: { changes: ChangeEvent[]; asof: string }) {
  const search = useGlobalSearch();
  const [all, setAll] = useState(false);
  const shown = all ? changes : changes.slice(0, CHANGES_SHOWN);
  const rest = changes.length - CHANGES_SHOWN;
  return (
    <Collapsible
      title={t('page.G1.changes')}
      section="changes"
      actions={
        changes.length > 0 ? (
          <MetaText
            kind="count"
            className="text-sm text-muted"
            k="page.G1.changesCount"
            params={{ n: changes.length }}
          />
        ) : undefined
      }
    >
      <Card className="flex flex-col gap-2">
        {changes.length === 0 ? (
          <EmptyState message={t('page.G1.noChanges')} />
        ) : (
          <>
            <ul aria-label={t('page.G1.changes')} className="flex flex-col divide-y divide-border">
              {shown.map((change) => {
                // 계약 .20 F5: 서버 summary 한 줄 — hash·json 이면 원값은 '바뀐 값 보기' 안, plain 은 summary 에 값이 있다
                const serverSummary = change.summary ?? null;
                const summaryOnly =
                  serverSummary !== null
                    ? change.value_kind !== 'hash' && change.value_kind !== 'json'
                    : change.field === 'first_load' && change.old_text === null;
                const head = (
                  <>
                    <span className="flex flex-wrap items-center gap-1.5">
                      <StatusPill tone={change.severity === 'critical' ? 'warn' : 'muted'}>
                        {enumText('page.common.severity', change.severity)}
                      </StatusPill>
                      {change.triggers_rejudge ? (
                        <StatusPill tone="neutral">{t('page.G1.rejudge')}</StatusPill>
                      ) : null}
                      <span className="font-semibold">
                        {change.complex_name ?? changeEntityText(change.entity)}
                      </span>
                      <span className="text-sm text-fg-2">
                        {serverSummary !== null ? (
                          <span title={change.field_label}>{serverSummary}</span>
                        ) : summaryOnly ? (
                          <>
                            <span>{changeFieldText(change.field)}</span>{' '}
                            <span>{changeValueText(change)}</span>
                          </>
                        ) : (
                          t('page.G1.changeSentence', { field: changeFieldText(change.field) })
                        )}
                      </span>
                    </span>
                    <span className="shrink-0 text-xs text-muted tabular-nums">
                      {formatDate(change.detected_at, asof)}
                    </span>
                  </>
                );
                return (
                  <li key={change.id} className="flex flex-col gap-1 py-3">
                    {change.complex_id ? (
                      <Link
                        to={`/complexes/${change.complex_id}${search}${change.tab ? `#${change.tab}` : ''}`}
                        className="flex flex-wrap items-center justify-between gap-2 text-fg hover:underline"
                      >
                        {head}
                      </Link>
                    ) : (
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        {head}
                      </div>
                    )}
                    {summaryOnly ? null : (
                      <details className="text-xs">
                        <summary className="cursor-pointer text-accent">
                          {t('page.G1.changeShowValue')}
                        </summary>
                        <span data-testid="change-value" className="break-all">
                          {changeValueText(change)}
                        </span>
                      </details>
                    )}
                  </li>
                );
              })}
            </ul>
            {rest > 0 ? (
              <button
                type="button"
                aria-expanded={all}
                onClick={() => setAll((x) => !x)}
                className="min-h-10 self-start rounded-xl border border-border px-4 py-2 text-sm font-semibold text-accent hover:border-accent"
              >
                {all ? (
                  t('page.G1.changesLess')
                ) : (
                  <MetaText kind="count" k="page.G1.changesMore" params={{ n: rest }} />
                )}
              </button>
            ) : null}
          </>
        )}
      </Card>
    </Collapsible>
  );
}
