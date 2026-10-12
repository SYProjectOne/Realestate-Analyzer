import type { ComplexDetail } from '@/api/types';
import {
  Badge,
  ExternalLink,
  FactCell,
  IntakeBadge,
  MetaValue,
  TieBadge,
  UnstableBadge,
  useOpenProvenance,
} from '@/components';
import { t } from '@/i18n';
import { enumText, JudgeScopeBadge, RejudgeNeededBadge } from '../_shared';
import {
  discountNote,
  discountShortNote,
  EstimatedDiscountNote,
  isEstimatedDiscount,
} from './tabs';

/** G3 ComplexHeader — 접수 배지 · 현재 구매가 범위 · 전매 D-day · 입주 · 포함 분류 · 종합 점수 */
export function ComplexHeader({ detail }: { detail: ComplexDetail }) {
  const { header, price, intake_current: intake, score, asof_date: asof } = detail;
  const openProvenance = useOpenProvenance();
  const intakeRaw = intake?.raw_document_id ?? null;
  return (
    <section
      aria-label={header.name}
      className="flex flex-col gap-3 rounded-sm border border-border bg-surface p-3"
    >
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-lg font-semibold">{header.name}</h2>
        {header.applyhome_id === null ? (
          // 계약 .15 F5(D20-2): 청약홈 공고 전 단지(applyhome_id null) — 트랙 A 면 공고 예정 후보. 판정 범위는 아래 배지(서버 값)
          <Badge tone="muted" title={t('page.G3.header.upcomingHint')} data-testid="upcoming-badge">
            {header.track === 'A' ? t('page.G3.header.upcoming') : t('page.G3.header.preNotice')}
          </Badge>
        ) : null}
        <IntakeBadge intake={intake} asof={asof} />
        {intakeRaw !== null && openProvenance ? (
          <button
            type="button"
            onClick={() => openProvenance(`rd_${intakeRaw}`)}
            className="text-xs underline"
          >
            {t('page.G3.header.intakeEvidence')}
          </button>
        ) : null}
        {score ? (
          <>
            {score.rank !== null ? (
              <Badge tone="strong">
                <MetaValue kind="rank" value={score.rank} as="rank" />
              </Badge>
            ) : null}
            <TieBadge tie={score.tie_group !== null} />
            <UnstableBadge unstable={score.unstable} />
            <JudgeScopeBadge scope={score.judge_scope} />
            <RejudgeNeededBadge needed={score.rejudge_needed} />
          </>
        ) : null}
        {header.official_site_url ? (
          <ExternalLink
            href={header.official_site_url}
            className="ml-auto text-sm underline"
            fallback={header.official_site_url}
          >
            {t('page.G3.header.officialSite')}
          </ExternalLink>
        ) : null}
      </div>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm md:grid-cols-4">
        <div className="flex flex-col">
          <dt className="text-xs text-muted">{t('page.G3.header.price')}</dt>
          <dd className="flex flex-wrap items-center gap-1">
            <FactCell fact={price.price_low} unit="won" />
            <span aria-hidden>~</span>
            <FactCell fact={price.price_high} unit="won" />
          </dd>
          {price.basis_type_code ? (
            <dd className="text-xs text-muted">
              {t('page.G3.header.priceBasis', { type: price.basis_type_code })}
            </dd>
          ) : null}
          {price.discount && price.discount.v !== null ? (
            <dd
              className="flex flex-wrap items-center gap-1 text-xs"
              data-testid="header-discount"
              title={discountNote(price) ?? undefined}
            >
              <span className="text-muted">{t('page.G3.header.discount')}</span>
              <FactCell fact={price.discount} unit="won" />
              {discountShortNote(price) ? (
                <span className="text-muted" data-testid="header-discount-note">
                  {discountShortNote(price)}
                </span>
              ) : null}
              {isEstimatedDiscount(price.discount) ? (
                // 계약 .13 F2(D16-1): 파서 할인은 '추정' — 안내 + G7 사람 확인 링크
                <EstimatedDiscountNote
                  complexId={header.id}
                  basisType={price.basis_type_code}
                  testId="header-discount-estimated"
                />
              ) : null}
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
