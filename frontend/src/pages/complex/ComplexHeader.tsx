import type { ComplexDetail } from '@/api/types';
import { Badge, FactCell, IntakeBadge, TieBadge, UnstableBadge } from '@/components';
import { t } from '@/i18n';
import { formatRank } from '@/lib/format';
import { enumText } from '../_shared';

/** G3 ComplexHeader — 접수 배지 · 현재 구매가 범위 · 전매 D-day · 입주 · 포함 분류 · 종합 점수 */
export function ComplexHeader({ detail }: { detail: ComplexDetail }) {
  const { header, price, intake_current: intake, score, asof_date: asof } = detail;
  return (
    <section
      aria-label={header.name}
      className="flex flex-col gap-3 rounded border border-border bg-surface p-3"
    >
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-lg font-semibold">{header.name}</h2>
        <IntakeBadge intake={intake} asof={asof} />
        {score ? (
          <>
            {score.rank !== null ? <Badge tone="strong">{formatRank(score.rank)}</Badge> : null}
            <TieBadge tie={score.tie_group !== null} />
            <UnstableBadge unstable={score.unstable} />
          </>
        ) : null}
        {header.official_site_url ? (
          <a
            href={header.official_site_url}
            target="_blank"
            rel="noreferrer noopener"
            className="ml-auto text-sm underline"
          >
            {t('page.G3.header.officialSite')}
          </a>
        ) : null}
      </div>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm md:grid-cols-4">
        <div className="flex flex-col">
          <dt className="text-xs text-muted">{t('page.G3.header.price')}</dt>
          <dd className="flex flex-wrap items-center gap-1">
            <FactCell fact={price.price_low} unit="won" showLabel={false} />
            <span aria-hidden>~</span>
            <FactCell fact={price.price_high} unit="won" />
          </dd>
          {price.basis_type_code ? (
            <dd className="text-xs text-muted">
              {t('page.G3.header.priceBasis', { type: price.basis_type_code })}
            </dd>
          ) : null}
        </div>
        <div className="flex flex-col">
          <dt className="text-xs text-muted">{t('page.G3.header.resaleEnd')}</dt>
          <dd>
            <FactCell
              fact={header.resale_end}
              unit="date"
              asof={asof}
              emptyReason={t('empty.unknown')}
            />
          </dd>
        </div>
        <div className="flex flex-col">
          <dt className="text-xs text-muted">{t('page.G3.header.moveIn')}</dt>
          <dd>
            <FactCell fact={header.move_in_ym} unit="ym" />
          </dd>
        </div>
        <div className="flex flex-col">
          <dt className="text-xs text-muted">{t('page.G3.header.total')}</dt>
          <dd>
            {score ? (
              <FactCell fact={score.total} unit="score" />
            ) : (
              <FactCell fact={null} unit="score" />
            )}
          </dd>
        </div>
        <div className="flex flex-col">
          <dt className="text-xs text-muted">{t('page.G3.header.address')}</dt>
          <dd>{header.address ?? t('empty.unknown')}</dd>
        </div>
        <div className="flex flex-col">
          <dt className="text-xs text-muted">{t('page.G3.header.livingArea')}</dt>
          <dd>{header.living_area_name ?? header.living_area ?? t('empty.unknown')}</dd>
        </div>
        <div className="flex flex-col">
          <dt className="text-xs text-muted">{t('page.G3.header.inclusion')}</dt>
          <dd className="flex flex-wrap items-center gap-1">
            {enumText('page.common.inclusion', header.inclusion_class)}
            <FactCell fact={header.inclusion_prob} unit="prob" />
          </dd>
        </div>
      </dl>
    </section>
  );
}
