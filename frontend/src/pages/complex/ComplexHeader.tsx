import type { ReactNode } from 'react';
import type { ComplexDetail, ScheduleItem } from '@/api/types';
import {
  Badge,
  EmptyState,
  ExternalLink,
  FactCell,
  IntakeBadge,
  MetaValue,
  Term,
  TieBadge,
  UnstableBadge,
  useOpenProvenance,
  type GlossaryKey,
} from '@/components';
import { Link } from 'react-router';
import { t } from '@/i18n';
import { useIsMobile } from '@/lib/useMediaQuery';
import {
  enumText,
  JudgeScopeBadge,
  NameWithProvenance,
  optionalFact,
  RejudgeNeededBadge,
  ScopeReason,
  useGlobalSearch,
} from '../_shared';
import {
  discountNote,
  discountShortNote,
  EstimatedDiscountNote,
  HeldPriceNote,
  heldBasisPrice,
  humanCheckTo,
  isEstimatedDiscount,
} from './tabs';

/**
 * 접수 사유(계약 데이터 모양 — 화면 문구는 ko.json). 둘 다 status '확인 불가'이고 그 원문은 접수 근거가 아니다.
 *  - 계약 .16·.17 F4(D21-5·D22-4) '공식 홈페이지가 다른 단지': 판정기(동일성 classify)가 auto `other_complex` — 다른 단지 페이지
 *  - 계약 .17 F4(D22-4·N11) '공식 홈페이지 동일성 미확인': 판정기가 review·unclear(미해결·불명) — 다른 단지라고 한 것이 아니다
 */
const SITE_OTHER_REASON = '공식 홈페이지가 다른 단지';
const SITE_UNCONFIRMED_REASON = '공식 홈페이지 동일성 미확인';

function siteIssue(intake: ComplexDetail['intake_current']): 'other' | 'unconfirmed' | null {
  if (intake?.status !== '확인 불가') return null;
  if (intake.reason === SITE_OTHER_REASON) return 'other';
  if (intake.reason === SITE_UNCONFIRMED_REASON) return 'unconfirmed';
  return null;
}

/** 정의 목록 한 칸(라벨 + 값) */
function Item({
  label,
  term,
  children,
  hint,
  className = '',
}: {
  label: ReactNode;
  /** 칸 제목 옆 용어 ⓘ(P6) — 화면에서 그 용어의 첫 등장에만 */
  term?: GlossaryKey;
  children: ReactNode;
  hint?: ReactNode;
  className?: string;
}) {
  return (
    <div className={`flex min-w-0 flex-col ${className}`}>
      <dt className="text-xs text-muted">
        {label}
        {term ? <Term k={term} /> : null}
      </dt>
      <dd className="flex flex-wrap items-center gap-1">{children}</dd>
      {hint ? <dd className="text-xs text-muted">{hint}</dd> : null}
    </div>
  );
}

/** 머리 안 한 단(3단 구획) — h3 + 본문. data-tier 로 순서를 테스트한다 */
function Tier({
  tier,
  title,
  children,
  className = '',
}: {
  tier: string;
  title: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      aria-label={title}
      data-tier={tier}
      className={`flex min-w-0 flex-col gap-2 rounded-sm border border-border p-3 ${className}`}
    >
      <h3 className="text-sm font-semibold">{title}</h3>
      {children}
    </section>
  );
}

/**
 * G3 ComplexHeader — R9-UI P1(30-proposal §2): 3단 머리.
 *  1단: 단지(이름·생활권·세대·입주·주소) → 지금 상태(접수·현재 적용 공고·일정·당첨 발표·계약)
 *  2단: 내야 할 돈(구매가·계약금·중도금·잔금) + 청약 전 꼭 볼 조건(전매 종료·거주의무·재당첨·규제·상한제·공급) → 점수·분류
 *  3단: 탭(index.tsx).
 * 값은 모두 API Fact 그대로(FactCell — 라벨·출처·확인일). 계약금 원 금액은 계약 .20(`down_payment_won`) 전까지 확인 불가.
 */
export function ComplexHeader({ detail }: { detail: ComplexDetail }) {
  const { header, price, intake_current: intake, score, asof_date: asof } = detail;
  const openProvenance = useOpenProvenance();
  const globalSearch = useGlobalSearch();
  const isMobile = useIsMobile();
  const intakeRaw = intake?.raw_document_id ?? null;
  const site = siteIssue(intake);
  const current = detail.payment.find((p) => p.is_current) ?? null;
  // 계약 .20(요청 Q1): 계약금 원 금액 — 오기 전엔 확인 불가(계산값 미제공). 프론트에서 곱하지 않는다
  const downWon = optionalFact(current, 'down_payment_won');
  const noticeProv = header.notice_date.prov;
  const address = header.address ?? t('empty.unknown');
  const livingArea = header.living_area_name ?? header.living_area ?? t('empty.unknown');
  return (
    <section
      aria-label={header.name}
      data-testid="complex-summary"
      className="flex flex-col gap-3 rounded-sm border border-border bg-surface p-3"
    >
      {/* 1단 — 단지 */}
      <div data-tier="identity" className="flex flex-col gap-1">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-lg font-semibold">
            {/* 계약 .16 F1(D21-8): 이름 클릭 → 이름 출처 서랍 + 라벨 배지(공고 예정 후보 '비공식'). 키 없으면 맨 이름 */}
            <NameWithProvenance source={header} />
          </h2>
          {header.applyhome_id === null ? (
            // 계약 .15 F5(D20-2): 청약홈 공고 전 단지(applyhome_id null) — 트랙 A 면 공고 예정 후보
            <Badge
              tone="muted"
              title={t('page.G3.header.upcomingHint')}
              data-testid="upcoming-badge"
            >
              {header.track === 'A' ? t('page.G3.header.upcoming') : t('page.G3.header.preNotice')}
            </Badge>
          ) : null}
          <span className="ml-auto flex flex-wrap items-center gap-3 text-sm">
            {noticeProv && openProvenance ? (
              <button
                type="button"
                onClick={() => openProvenance(noticeProv)}
                className="underline"
                data-testid="notice-original"
              >
                {t('page.G3.summary.noticeOriginal')}
              </button>
            ) : null}
            {header.official_site_url ? (
              <ExternalLink
                href={header.official_site_url}
                className="underline"
                fallback={header.official_site_url}
              >
                {t('page.G3.header.officialSite')}
              </ExternalLink>
            ) : null}
          </span>
        </div>
        <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
          <span>{livingArea}</span>
          <span aria-hidden>·</span>
          <span className="text-muted">{t('page.G3.summary.unitsTotal')}</span>
          <FactCell wrap fact={header.units_total} unit="households" />
          <span aria-hidden>·</span>
          <span className="text-muted">{t('page.G3.header.moveIn')}</span>
          <FactCell wrap fact={header.move_in_ym} unit="ym" />
        </p>
        {isMobile ? (
          <details className="text-sm">
            <summary className="cursor-pointer text-muted">{t('page.G3.summary.info')}</summary>
            <p>
              <span className="text-muted">{t('page.G3.header.address')}</span> {address}
            </p>
          </details>
        ) : (
          <p className="text-sm">
            <span className="text-muted">{t('page.G3.header.address')}</span> {address}
          </p>
        )}
      </div>

      {/* 1단 — 지금 상태 */}
      <Tier tier="status" title={t('page.G3.summary.status')}>
        <div className="flex flex-wrap items-center gap-2">
          <IntakeBadge intake={intake} asof={asof} />
          <Term k="intake_status" />
          {intakeRaw !== null && openProvenance ? (
            <button
              type="button"
              onClick={() => openProvenance(`rd_${intakeRaw}`)}
              className="text-xs underline"
            >
              {site === 'other'
                ? t('page.G3.header.siteOtherEvidence')
                : site === 'unconfirmed'
                  ? t('page.G3.header.siteUnconfirmedEvidence')
                  : t('page.G3.header.intakeEvidence')}
            </button>
          ) : null}
          {current?.notice_kind ? (
            <span className="text-sm" data-testid="current-notice">
              {t('page.G3.summary.currentNotice', { kind: current.notice_kind })}
            </span>
          ) : null}
        </div>
        {site !== null ? (
          <p
            className="text-xs text-muted"
            data-testid={site === 'other' ? 'site-other-note' : 'site-unconfirmed-note'}
          >
            {site === 'other'
              ? t('page.G3.header.siteOtherHint')
              : t('page.G3.header.siteUnconfirmedHint')}{' '}
            <Link to={humanCheckTo(globalSearch, header.id, 'intake_status')} className="underline">
              {t('page.G3.header.siteOtherHumanCheck')}
            </Link>
          </p>
        ) : null}
        <dl className="grid gap-x-4 gap-y-2 text-sm sm:grid-cols-[auto_1fr]">
          <dt className="text-xs text-muted sm:pt-0.5">{t('page.G3.summary.schedule')}</dt>
          <dd className="flex flex-col gap-1" data-testid="apply-dates">
            {header.apply_dates.length === 0 ? (
              <EmptyState inline reason={t('page.G3.summary.noScheduleReason')} />
            ) : (
              header.apply_dates.map((item, i) => <ScheduleRow key={i} item={item} asof={asof} />)
            )}
          </dd>
          <dt className="text-xs text-muted sm:pt-0.5">{t('page.G3.summary.winnerDate')}</dt>
          <dd>
            <FactCell wrap fact={header.winner_date} unit="date" asof={asof} />
          </dd>
          {header.contract_dates.length > 0 ? (
            <>
              <dt className="text-xs text-muted sm:pt-0.5">{t('page.G3.summary.contract')}</dt>
              <dd className="flex flex-col gap-1">
                {header.contract_dates.map((item, i) => (
                  <ScheduleRow key={i} item={item} asof={asof} />
                ))}
              </dd>
            </>
          ) : null}
        </dl>
      </Tier>

      {/* 2단 — 내야 할 돈 + 청약 전 꼭 볼 조건(기본 펼침, D28-4) */}
      <div className="grid gap-3 md:grid-cols-2">
        <Tier tier="money" title={t('page.G3.summary.money')}>
          <dl className="flex flex-col gap-2 text-sm">
            <div className="flex flex-col">
              <dt className="text-xs text-muted">
                {t('page.G3.header.price')}
                <Term k="current_price" />
              </dt>
              <dd className="flex flex-wrap items-center gap-1">
                <FactCell wrap fact={price.price_low} unit="won" />
                <span aria-hidden>~</span>
                <FactCell wrap fact={price.price_high} unit="won" />
              </dd>
              {price.basis_type_code ? (
                <dd className="text-xs text-muted">
                  {t('page.G3.header.priceBasis', { type: price.basis_type_code })}
                </dd>
              ) : null}
              {price.composition ? (
                <dd className="text-xs text-muted" data-testid="price-composition">
                  {t('page.G3.summary.priceComposition')}: {price.composition}
                </dd>
              ) : null}
              {/* 계약 .16 F6·.17 F3(D21-1·D22-5): 기준 타입 가격 채택 보류 — 보류 출처 + 사람 확인 링크 */}
              {heldBasisPrice(detail) ? (
                <dd>
                  <HeldPriceNote detail={detail} testId="held-price-note" />
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
          </dl>
          {/* 정의 목록은 dt·dd(또는 그것을 묶은 div)만 바로 안에 — 납부 항목은 별도 목록(접근성 definition-list) */}
          <dl className="grid gap-x-4 gap-y-2 text-sm sm:grid-cols-2">
            {current ? (
              <>
                <Item label={t('page.G3.summary.down')} term="down">
                  <FactCell wrap fact={current.down_payment_pct} unit="pct" digits={0} />
                  <span className="text-xs text-muted">{t('page.G3.summary.downFirst')}</span>
                  <FactCell wrap fact={current.down_payment_first_won} unit="won" />
                </Item>
                <Item label={t('page.G3.summary.downWon')}>
                  <FactCell
                    wrap
                    fact={downWon}
                    unit="won"
                    emptyReason={t('page.G3.summary.downWonMissing')}
                  />
                </Item>
                <Item
                  label={t('page.G3.summary.interim')}
                  term="interim"
                  hint={
                    current.interim_terms_text
                      ? t('page.G3.summary.interimTerms', { text: current.interim_terms_text })
                      : undefined
                  }
                >
                  <FactCell wrap fact={current.interim_pct} unit="pct" digits={0} />
                </Item>
                <Item label={t('page.G3.summary.balance')} term="balance">
                  <FactCell wrap fact={current.balance_pct} unit="pct" digits={0} />
                </Item>
              </>
            ) : (
              <Item label={t('page.G3.summary.down')}>
                <EmptyState inline reason={t('page.G3.summary.noPayment')} />
              </Item>
            )}
          </dl>
          <Link
            to={{ pathname: `/complexes/${header.id}`, search: globalSearch, hash: '#payment' }}
            replace
            className="self-start text-sm underline"
          >
            {t('page.G3.summary.moreMoney')}
          </Link>
        </Tier>

        <Tier tier="conditions" title={t('page.G3.summary.conditions')}>
          <p className="text-xs text-muted">{t('page.G3.summary.conditionsHint')}</p>
          <dl className="grid gap-x-4 gap-y-2 text-sm sm:grid-cols-2">
            <Item
              label={t('page.G3.header.resaleEnd')}
              term="resale_end"
              hint={t('page.G3.summary.resaleEndPlain')}
              className="sm:col-span-2"
            >
              <FactCell
                wrap
                fact={header.resale_end}
                unit="date"
                asof={asof}
                emptyReason={t('empty.unknown')}
              />
            </Item>
            <Item label={t('page.G3.summary.residency')} term="residency">
              <FactCell wrap fact={header.residency_months} unit="months" />
            </Item>
            <Item label={t('page.G3.summary.rewin')} term="rewin">
              <FactCell wrap fact={header.rewin_restriction_years} unit="years" />
            </Item>
            <Item label={t('page.G3.summary.regulated')} term="regulated">
              <FactCell wrap fact={header.regulated} unit="text" />
            </Item>
            <Item label={t('page.G3.summary.priceCap')} term="price_cap">
              <FactCell wrap fact={header.price_cap} unit="text" />
            </Item>
            <Item
              label={t('page.G3.summary.supply')}
              term="special_supply"
              hint={t('page.G3.summary.specialHint')}
              className="sm:col-span-2"
            >
              <span className="text-xs text-muted">{t('page.G3.summary.unitsGeneral')}</span>
              <FactCell wrap fact={header.units_general} unit="households" />
              <span className="text-xs text-muted">{t('page.G3.summary.unitsSpecial')}</span>
              <FactCell wrap fact={header.units_special} unit="households" />
            </Item>
          </dl>
        </Tier>
      </div>

      {/* 2단 — 점수·분류(사실 뒤, D28-4) */}
      <Tier tier="score" title={t('page.G3.summary.score')}>
        <dl className="grid gap-x-4 gap-y-2 text-sm md:grid-cols-3">
          <Item label={t('page.G3.header.total')} term="total">
            {score ? (
              <>
                <FactCell wrap fact={score.total} unit="score" />
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
            ) : (
              <FactCell fact={null} unit="score" />
            )}
          </Item>
          {score?.delta_rerank ? (
            <Item label={t('page.common.deltaRerank')}>
              <FactCell wrap fact={score.delta_rerank} unit="score" />
            </Item>
          ) : null}
          <Item label={t('page.G3.header.inclusion')} term="inclusion">
            {enumText('page.common.inclusion', header.inclusion_class)}
            <FactCell wrap fact={header.inclusion_prob} unit="prob" />
          </Item>
          {header.judge_scope_reason ? (
            // 계약 .17 F1(D22-5): 판정 범위 사유 — 서버 문자열 그대로(목록 행과 같은 값). 키 없음(.16 저장본)이면 칸 없음
            <Item
              label={t('page.G3.header.scopeReason')}
              term="judge_scope"
              className="md:col-span-3"
            >
              <ScopeReason
                reason={header.judge_scope_reason}
                rejudgeNeeded={score?.rejudge_needed ?? false}
                testId="scope-reason"
              />
            </Item>
          ) : null}
        </dl>
      </Tier>
      <p className="text-xs text-muted" data-testid="not-qualification">
        {t('page.G3.summary.notQualification')}
      </p>
    </section>
  );
}

/** 일정 한 줄: 종류(서버 값 그대로) · 시작 ~ 끝(D±) */
function ScheduleRow({ item, asof }: { item: ScheduleItem; asof: string }) {
  return (
    <span className="flex flex-wrap items-center gap-1">
      <span className="text-xs text-muted">{item.kind}</span>
      <FactCell wrap fact={item.start} unit="date" asof={asof} />
      {item.end ? (
        <>
          <span aria-hidden>~</span>
          <FactCell wrap fact={item.end} unit="date" asof={asof} />
        </>
      ) : null}
    </span>
  );
}
