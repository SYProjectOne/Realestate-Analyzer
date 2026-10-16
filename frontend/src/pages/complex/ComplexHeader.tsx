import type { ReactNode } from 'react';
import { Link } from 'react-router';
import type { ComplexDetail, Fact } from '@/api/types';
import {
  Badge,
  BigNumber,
  Card,
  EmptyState,
  ExternalLink,
  FactCell,
  FactList,
  FactRow,
  IntakeBadge,
  KeepNote,
  MetaText,
  Term,
  useOpenProvenance,
} from '@/components';
import { t, tDynamic } from '@/i18n';
import { kstDay } from '@/lib/format';
import { useIsMobile } from '@/lib/useMediaQuery';
import { NameWithProvenance, useGlobalSearch } from '../_shared';
import { CompetitionCard } from './CompetitionSummaryLine';
import { ScheduleCard } from './ScheduleCard';
import { ScoreCard } from './ScoreCard';
import { Tier } from './Tier';
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

/** 목업 버튼 모양(주 버튼 = 진한 바탕, 보조 = 테두리) */
const BTN =
  'inline-flex min-h-10 items-center justify-center gap-1.5 rounded-xl border px-4 text-sm font-semibold';
const BTN_PRIMARY = `${BTN} border-fg bg-fg text-bg hover:opacity-90`;
const BTN_SECONDARY = `${BTN} border-border-strong bg-surface text-fg hover:border-accent`;

/**
 * G3 ComplexHeader — R11(D30, 보드 Detail · Mobile): 질문형 구역.
 *  머리 카드(접수 알약 · 이름 · 생활권·세대·입주 · 주소 · 지금 상태 사실 줄 · 원문 버튼) + 가격 카드(현재 구매가 · 주변 거래 비교)
 *  → 언제, 얼마를 내야 하나요?(납부 띠 + 카드 3) → 청약 전에 꼭 확인할 조건(칸 5) → 일정은 어디쯤 왔나요?(진행 줄)
 *  → 청약 때 얼마나 몰렸나요?(경쟁률 요약) · 점수는 왜 이렇게 나왔나요?(성분 · 비중) → 탭(index.tsx).
 * 값은 모두 API Fact 그대로(FactCell — 라벨·출처·확인일). 화면은 계산하지 않고 판단 문장을 짓지 않는다(규칙 3·5, D30-7).
 */
export function ComplexHeader({ detail }: { detail: ComplexDetail }) {
  const { header } = detail;
  return (
    <section
      aria-label={header.name}
      data-testid="complex-summary"
      className="flex min-w-0 flex-col gap-4"
    >
      <div className="grid min-w-0 gap-4 lg:grid-cols-[minmax(0,1.8fr)_minmax(0,1fr)]">
        <IdentityCard detail={detail} />
        <PriceCard detail={detail} />
      </div>
      <MoneyCard detail={detail} />
      <ConditionsCard detail={detail} />
      <ScheduleCard detail={detail} />
      <div className="grid min-w-0 gap-4 lg:grid-cols-2">
        <CompetitionCard detail={detail} />
        <ScoreCard detail={detail} />
      </div>
      <p className="text-xs text-muted" data-testid="not-qualification">
        {t('page.G3.summary.notQualification')}
      </p>
    </section>
  );
}

/** 머리 카드: 접수 알약 · 이름 · 생활권·세대·입주 · 주소 · 지금 상태(사실 줄) · 원문 버튼 */
function IdentityCard({ detail }: { detail: ComplexDetail }) {
  const { header, intake_current: intake, asof_date: asof } = detail;
  const openProvenance = useOpenProvenance();
  const globalSearch = useGlobalSearch();
  const isMobile = useIsMobile();
  const intakeRaw = intake?.raw_document_id ?? null;
  const site = siteIssue(intake);
  const noticeProv = header.notice_date.prov;
  const address = header.address ?? t('empty.unknown');
  const livingArea = header.living_area_name ?? header.living_area ?? t('empty.unknown');
  return (
    <Card padding="lg" data-tier="identity" className="flex min-w-0 flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <IntakeBadge intake={intake} asof={asof} />
        <Term k="intake_status" />
        {header.applyhome_id === null ? (
          // 계약 .15 F5(D20-2): 청약홈 공고 전 단지(applyhome_id null) — 트랙 A 면 공고 예정 후보
          <Badge tone="muted" title={t('page.G3.header.upcomingHint')} data-testid="upcoming-badge">
            {header.track === 'A' ? t('page.G3.header.upcoming') : t('page.G3.header.preNotice')}
          </Badge>
        ) : null}
      </div>
      <div className="flex min-w-0 flex-col gap-2">
        <h2
          data-testid="complex-name"
          className="text-2xl font-bold leading-tight tracking-tight text-fg sm:text-[30px]"
        >
          {/* 계약 .16 F1(D21-8): 이름 클릭 → 이름 출처 서랍 + 라벨 배지(공고 예정 후보 '비공식'). 키 없으면 맨 이름 */}
          <NameWithProvenance source={header} />
        </h2>
        <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[15px] text-fg-2">
          <span className="text-muted">{t('page.G3.header.livingArea')}</span>
          <span className="font-semibold text-fg">{livingArea}</span>
          <span aria-hidden>·</span>
          <span className="text-muted">{t('page.G3.summary.unitsTotal')}</span>
          <FactCell wrap fact={header.units_total} unit="households" />
          <span className="inline-flex flex-wrap items-center gap-1 text-sm">
            <span aria-hidden>(</span>
            <span className="text-muted">{t('page.G3.summary.unitsGeneral')}</span>
            <FactCell wrap fact={header.units_general} unit="households" />
            <span aria-hidden>·</span>
            <span className="text-muted">{t('page.G3.summary.unitsSpecial')}</span>
            <FactCell wrap fact={header.units_special} unit="households" />
            <Term k="special_supply" />
            <span aria-hidden>)</span>
          </span>
          <span aria-hidden>·</span>
          <span className="text-muted">{t('page.G3.header.moveIn')}</span>
          <FactCell wrap fact={header.move_in_ym} unit="ym" />
        </p>
        {isMobile ? (
          <details className="text-sm">
            <summary className="cursor-pointer text-muted">{t('page.G3.summary.info')}</summary>
            <p className="mt-1">
              <span className="text-muted">{t('page.G3.header.address')}</span> {address}
            </p>
          </details>
        ) : (
          <p className="text-sm text-fg-2">
            <span className="text-muted">{t('page.G3.header.address')}</span> {address}
          </p>
        )}
      </div>

      {/* 지금 상태 — D30-7: 서버 필드를 이어 붙인 사실 줄(현재 적용 공고 · 접수 상태 · 확인 경로 · 확인일). 판단 문장 없음 */}
      <section
        aria-label={t('page.G3.summary.status')}
        data-tier="status"
        className="flex flex-col gap-2 rounded-xl bg-subtle px-4 py-3 text-sm"
      >
        <StatusFacts detail={detail} />
        {site !== null ? (
          <p
            className="text-xs text-muted"
            data-testid={site === 'other' ? 'site-other-note' : 'site-unconfirmed-note'}
          >
            {site === 'other'
              ? t('page.G3.header.siteOtherHint')
              : t('page.G3.header.siteUnconfirmedHint')}{' '}
            <Link
              to={humanCheckTo(globalSearch, header.id, 'intake_status')}
              className="font-medium text-accent underline"
            >
              {t('page.G3.header.siteOtherHumanCheck')}
            </Link>
          </p>
        ) : null}
      </section>

      <div className="flex flex-wrap items-center gap-2">
        {noticeProv && openProvenance ? (
          <button
            type="button"
            onClick={() => openProvenance(noticeProv)}
            className={BTN_PRIMARY}
            data-testid="notice-original"
          >
            {t('page.G3.summary.noticeOriginal')}
          </button>
        ) : null}
        {header.official_site_url ? (
          <ExternalLink
            href={header.official_site_url}
            className={BTN_SECONDARY}
            fallback={header.official_site_url}
          >
            {t('page.G3.header.officialSite')}
          </ExternalLink>
        ) : null}
        {intakeRaw !== null && openProvenance ? (
          <button
            type="button"
            onClick={() => openProvenance(`rd_${intakeRaw}`)}
            className={BTN_SECONDARY}
          >
            {site === 'other'
              ? t('page.G3.header.siteOtherEvidence')
              : site === 'unconfirmed'
                ? t('page.G3.header.siteUnconfirmedEvidence')
                : t('page.G3.header.intakeEvidence')}
          </button>
        ) : null}
      </div>
    </Card>
  );
}

/** 사실 줄: "현재 적용 공고: 무순위 (적용 시작 2026.01.26 확인됨)" · "접수 상태: 접수 가능 (공식 팝업 · 2026-10-13 확인)" */
function StatusFacts({ detail }: { detail: ComplexDetail }) {
  const intake = detail.intake_current;
  const current = detail.payment.find((p) => p.is_current) ?? null;
  const checked = intake?.checked_at ? kstDay(intake.checked_at) : null;
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-1">
      {current?.notice_kind ? (
        <p className="flex flex-wrap items-center gap-1">
          <span className="font-semibold" data-testid="current-notice">
            {t('page.G3.summary.currentNotice', { kind: current.notice_kind })}
          </span>
          <span className="text-xs text-muted">{t('page.G3.summary.effectiveFrom')}</span>
          <FactCell wrap fact={current.effective_from} unit="date" />
        </p>
      ) : null}
      <p className="flex flex-wrap items-center gap-1" data-testid="status-intake">
        <span className="text-muted">{t('page.G3.summary.intake')}</span>
        {intake ? (
          <>
            <span className="font-semibold">
              {tDynamic(`intake.status.${intake.status}`, intake.status)}
            </span>
            <span className="text-xs text-muted">
              {checked
                ? t('page.G3.summary.intakeVia', {
                    path: tDynamic(`intake.path.${intake.path}`, intake.path),
                    date: checked,
                  })
                : tDynamic(`intake.path.${intake.path}`, intake.path)}
            </span>
          </>
        ) : (
          <span className="font-semibold">{t('intake.none')}</span>
        )}
      </p>
    </div>
  );
}

/** 가격 카드: 현재 구매가(큰 값) · 기준 타입 · 구성 · 보류·할인 메모 · 주변 거래 비교(gap_pct · 가운데값 · comps_median · 비교 단지 수) */
function PriceCard({ detail }: { detail: ComplexDetail }) {
  const { price, gap, header } = detail;
  const globalSearch = useGlobalSearch();
  return (
    <Card padding="lg" data-tier="price" className="flex min-w-0 flex-col gap-3">
      <BigNumber
        size="xl"
        data-testid="header-price"
        label={
          <span className="inline-flex flex-wrap items-center gap-1">
            {t('page.G3.header.price')}
            {price.basis_type_code ? (
              <span>· {t('page.G3.header.priceBasis', { type: price.basis_type_code })}</span>
            ) : null}
            <Term k="current_price" />
          </span>
        }
      >
        <span className="inline-flex flex-wrap items-baseline gap-x-2 gap-y-1">
          <FactCell wrap fact={price.price_low} unit="won" />
          <span aria-hidden>~</span>
          <FactCell wrap fact={price.price_high} unit="won" />
        </span>
      </BigNumber>
      {price.composition ? (
        <p className="text-xs text-muted" data-testid="price-composition">
          {t('page.G3.summary.priceComposition')}: {price.composition}
        </p>
      ) : null}
      {/* 계약 .16 F6·.17 F3(D21-1·D22-5): 기준 타입 가격 채택 보류 — 보류 출처 + 사람 확인 링크 */}
      {heldBasisPrice(detail) ? <HeldPriceNote detail={detail} testId="held-price-note" /> : null}
      {price.discount && price.discount.v !== null ? (
        <p
          className="flex flex-wrap items-center gap-1 text-xs"
          data-testid="header-discount"
          title={discountNote(price) ?? undefined}
        >
          <span className="text-muted">{t('page.G3.header.discount')}</span>
          <FactCell fact={price.discount} unit="won" />
          {discountShortNote(price) ? (
            <span className="font-medium" data-testid="header-discount-note">
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
        </p>
      ) : null}
      <div className="mt-1 flex flex-col gap-2 rounded-xl border border-border px-4 py-3">
        <h3 className="text-sm font-semibold text-fg">{t('page.G3.gapMini.title')}</h3>
        <FactList aria-label={t('page.G3.gapMini.title')}>
          <FactRow
            label={
              <span className="inline-flex items-center gap-1">
                {t('page.G3.gap.pct')}
                <Term k="gap" />
              </span>
            }
          >
            <FactCell wrap fact={gap.gap_pct} unit="pct" />
          </FactRow>
          <FactRow label={t('page.G3.gapMini.mid')}>
            <FactCell wrap fact={price.price_mid} unit="won" />
          </FactRow>
          <FactRow label={t('page.G3.gap.compsMedian')} data-testid="gap-mini-comps-median">
            {/* 계약 .22 F2(D30-5): 비교군 전체 중앙값 — 서버 저장값 그대로(comps[] 를 묶지 않는다). 키 없음 = .22 전 저장본 */}
            <FactCell
              wrap
              fact={gap.comps_median ?? null}
              unit="won"
              emptyReason={t('page.G3.gapMini.compsMedianOld')}
            />
          </FactRow>
          <FactRow label={t('page.G3.gapMini.comps')}>
            <MetaText
              kind="count"
              k="page.G3.gapMini.compsCount"
              params={{ n: gap.comps.length }}
            />
          </FactRow>
        </FactList>
        <Link
          to={{ pathname: `/complexes/${header.id}`, search: globalSearch, hash: '#gap' }}
          replace
          className="self-start text-sm font-medium text-accent hover:underline"
        >
          {t('page.G3.gapMini.more')}
        </Link>
      </div>
    </Card>
  );
}

/** 납부 비율 Fact 값(띠 그래프 폭) — 서버 비율 그대로, 숫자가 아니면 0(그리지 않음) */
function pctWidth(fact: Fact | null | undefined): number {
  const v = Number(fact?.v);
  return Number.isFinite(v) && v > 0 ? Math.min(v, 100) : 0;
}

/** 언제, 얼마를 내야 하나요? — 납부 띠(장식) + 계약금·중도금·잔금 카드(비율 · 원 금액 = 서버 산술 Fact) */
function MoneyCard({ detail }: { detail: ComplexDetail }) {
  const { header, price } = detail;
  const globalSearch = useGlobalSearch();
  const current = detail.payment.find((p) => p.is_current) ?? null;
  // 계약 .20 F1: 계약금·중도금·잔금 원 금액 = 서버 산술 Fact(추정(산술(중간 가격 × 비율))). 옛 저장본(키 없음)은
  // 확인 불가(계산값 없음). 프론트에서 곱하지 않는다
  const amounts = price.payment_amounts ?? null;
  const missingWon = t('page.G3.summary.downWonMissing');
  return (
    <Tier
      tier="money"
      title={t('page.G3.summary.money')}
      hint={t('page.G3.summary.moneyHint')}
      actions={amounts ? <Badge tone="dashed">{t('page.G3.summary.moneyLabel')}</Badge> : null}
    >
      {current ? (
        <>
          {/* 띠 = 공고 비율 그대로(장식 — 값·라벨은 아래 카드의 FactCell) */}
          <div
            aria-hidden
            data-testid="payment-band"
            className="flex h-9 w-full overflow-hidden rounded-lg bg-chip"
          >
            <span
              className="h-full bg-fg"
              style={{ width: `${pctWidth(current.down_payment_pct)}%` }}
            />
            <span
              className="h-full bg-accent"
              style={{ width: `${pctWidth(current.interim_pct)}%` }}
            />
            <span
              className="h-full bg-accent-soft"
              style={{ width: `${pctWidth(current.balance_pct)}%` }}
            />
          </div>
          <ul className="grid gap-3 sm:grid-cols-3">
            <MoneyItem
              swatch="bg-fg"
              label={t('page.G3.summary.down')}
              term="down"
              pct={current.down_payment_pct}
              won={amounts?.down_payment_won ?? null}
              missing={missingWon}
              when={t('page.G3.summary.downWhen')}
            >
              <span className="flex flex-wrap items-center gap-1">
                <span>{t('page.G3.summary.downFirst')}</span>
                <FactCell
                  wrap
                  fact={amounts?.down_payment_first_won ?? current.down_payment_first_won}
                  unit="won"
                />
              </span>
            </MoneyItem>
            <MoneyItem
              swatch="bg-accent"
              label={t('page.G3.summary.interim')}
              term="interim"
              pct={current.interim_pct}
              won={amounts?.interim_won ?? null}
              missing={missingWon}
              when={t('page.G3.summary.interimWhen')}
            >
              {current.interim_terms_text ? (
                <span>
                  {t('page.G3.summary.interimTerms', { text: current.interim_terms_text })}
                </span>
              ) : null}
            </MoneyItem>
            <MoneyItem
              swatch="bg-accent-soft"
              label={t('page.G3.summary.balance')}
              term="balance"
              pct={current.balance_pct}
              won={amounts?.balance_won ?? null}
              missing={missingWon}
              when={
                <span className="inline-flex flex-wrap items-center gap-1">
                  {t('page.G3.summary.balanceWhen')}
                  <FactCell wrap fact={header.move_in_ym} unit="ym" />
                </span>
              }
            />
          </ul>
        </>
      ) : (
        <p className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-muted">{t('page.G3.summary.down')}</span>
          <EmptyState inline reason={t('page.G3.summary.noPayment')} />
        </p>
      )}
      <div className="flex flex-wrap items-center justify-between gap-2">
        {amounts?.formula ? (
          // 계산식(서버 문구) — 금액 칸을 누르면 출처(현재 구매가 가운데값)·라벨 '추정(산술(…))'
          <p className="text-xs text-muted" data-testid="payment-formula" title={amounts.formula}>
            {t('page.G3.summary.formula', { formula: amounts.formula })}
          </p>
        ) : (
          <span />
        )}
        <Link
          to={{ pathname: `/complexes/${header.id}`, search: globalSearch, hash: '#payment' }}
          replace
          className="text-sm font-medium text-accent hover:underline"
        >
          {t('page.G3.summary.moreMoney')}
        </Link>
      </div>
    </Tier>
  );
}

function MoneyItem({
  swatch,
  label,
  term,
  pct,
  won,
  missing,
  when,
  children,
}: {
  swatch: string;
  label: string;
  term: 'down' | 'interim' | 'balance';
  pct: Fact;
  won: Fact | null;
  missing: string;
  when: ReactNode;
  children?: ReactNode;
}) {
  return (
    <li className="flex min-w-0 flex-col gap-2 rounded-[14px] border border-border p-4">
      <span className="flex flex-wrap items-center gap-1.5 text-[13px] text-fg-2">
        <span aria-hidden className={`size-2.5 shrink-0 rounded-sm ${swatch}`} />
        <span>{label}</span>
        <FactCell wrap fact={pct} unit="pct" digits={0} />
        <Term k={term} />
      </span>
      <span className="text-xl font-bold leading-tight text-fg sm:text-2xl">
        <FactCell wrap fact={won} unit="won" emptyReason={missing} />
      </span>
      <span className="text-[13px] text-fg-2">{when}</span>
      {children ? <span className="text-xs text-muted">{children}</span> : null}
    </li>
  );
}

/** 값이 정확히 0이면 쉬운 말(ko.json 표시 매핑 — 판단이 아니라 값 → 글자), 아니면 null */
function zeroText(fact: Fact | null | undefined, text: string): string | null {
  return fact && fact.v !== null && Number(fact.v) === 0 ? text : null;
}

/** 청약 전에 꼭 확인할 조건 — 되팔기(전매) · 실거주 · 재당첨 · 규제지역 · 분양가 상한제 칸 */
function ConditionsCard({ detail }: { detail: ComplexDetail }) {
  const { header, asof_date: asof } = detail;
  const residencyZero = zeroText(header.residency_months, t('page.G3.summary.residencyNone'));
  const rewinZero = zeroText(header.rewin_restriction_years, t('page.G3.summary.rewinNone'));
  return (
    <Tier
      tier="conditions"
      title={t('page.G3.summary.conditions')}
      hint={t('page.G3.summary.conditionsHint')}
    >
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <KeepNote
          data-testid="cond-resale"
          label={t('page.G3.header.resaleEnd')}
          term="resale_end"
          value={
            <FactCell
              wrap
              fact={header.resale_end}
              unit="date"
              asof={asof}
              emptyReason={t('empty.unknown')}
            />
          }
          detail={t('page.G3.summary.resaleEndPlain')}
        />
        <KeepNote
          data-testid="cond-residency"
          label={t('page.G3.summary.residency')}
          term="residency"
          value={residencyZero ?? <FactCell wrap fact={header.residency_months} unit="months" />}
          detail={
            residencyZero ? (
              <FactCell wrap fact={header.residency_months} unit="months" />
            ) : undefined
          }
        />
        <KeepNote
          data-testid="cond-rewin"
          label={t('page.G3.summary.rewin')}
          term="rewin"
          value={rewinZero ?? <FactCell wrap fact={header.rewin_restriction_years} unit="years" />}
          detail={
            rewinZero ? (
              <FactCell wrap fact={header.rewin_restriction_years} unit="years" />
            ) : undefined
          }
        />
        <KeepNote
          data-testid="cond-regulated"
          label={t('page.G3.summary.regulated')}
          term="regulated"
          value={<FactCell wrap fact={header.regulated} unit="text" />}
        />
        <KeepNote
          data-testid="cond-price-cap"
          label={t('page.G3.summary.priceCap')}
          term="price_cap"
          value={<FactCell wrap fact={header.price_cap} unit="text" />}
        />
      </div>
      <p className="rounded-xl bg-subtle px-4 py-2.5 text-[13px] text-fg-2">
        {t('page.G3.summary.termTip')} · {t('page.G3.summary.specialHint')}
      </p>
    </Tier>
  );
}
