import { useId, useState } from 'react';
import { useCanWrite } from '@/api/auth';
import { ApiError } from '@/api/client';
import { useComplexes, useUpdateCatalystLocation } from '@/api/hooks';
import type {
  CatalystLinkView,
  CatalystPatch,
  CatalystUpdated,
  CatalystView,
  Fact,
  Market,
} from '@/api/types';
import { Badge, FactCell, MetaValue, PublishJobProgress } from '@/components';
import { t } from '@/i18n';
import { enumText, Section, tdClass, thClass } from '../_shared';

/** 위도·경도 문자열 검사(빈 값 허용). 범위 밖·숫자 아님이면 오류 문구 */
export function parseCoord(raw: string, kind: 'lat' | 'lon'): number | null | 'invalid' {
  const v = raw.trim();
  if (!v) return null;
  if (!/^-?\d+(\.\d+)?$/.test(v)) return 'invalid';
  const n = Number(v);
  const limit = kind === 'lat' ? 90 : 180;
  return Math.abs(n) <= limit ? n : 'invalid';
}

/** 예상 시기 YYYY-MM(빈 값 허용) */
export function parseYm(raw: string): string | null | 'invalid' {
  const v = raw.trim();
  if (!v) return null;
  return /^\d{4}-(0[1-9]|1[0-2])$/.test(v) ? v : 'invalid';
}

type LivingAreaRef = Pick<Market['living_areas'][number], 'id' | 'name'>;

/**
 * 서버 연결 근거 문구의 생활권 id(`la_1` 같은 내부 식별자)를 생활권 이름으로 바꾼다(4차 리뷰 minor) —
 * 화면에 내부 id 를 보이지 않는다. 앞뒤가 영문·숫자·밑줄이 아닌 온전한 토큰만 바꾼다(`la_1` ≠ `la_10`).
 */
export function livingAreaReason(
  reason: string | null | undefined,
  areas: readonly LivingAreaRef[],
): string | null {
  if (!reason) return reason ?? null;
  const byId = new Map(areas.map((a) => [a.id, a.name]));
  if (byId.size === 0) return reason;
  const ids = [...byId.keys()]
    .sort((a, b) => b.length - a.length)
    .map((id) => id.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  const re = new RegExp(`(?<![A-Za-z0-9_])(${ids.join('|')})(?![A-Za-z0-9_])`, 'g');
  return reason.replace(re, (id) => byId.get(id) ?? id);
}

/**
 * 링크 거리 → Fact(라벨은 서버가 준 link.label). 좌표 없는 단지는 distance_m=null → '확인 불가(<서버 reason>)'
 * — reason 은 서버가 정한 연결 근거('같은 생활권(…, 단지 좌표 없음)'·'사람 지정(단지 좌표 없음)'), 생활권 id 는 이름으로.
 */
export function distanceFact(link: CatalystLinkView, areas: readonly LivingAreaRef[] = []): Fact {
  return {
    v: link.distance_m,
    label: link.distance_m === null ? '확인 불가' : link.label,
    reason:
      link.distance_m === null
        ? (livingAreaReason(link.reason, areas) ?? t('page.G6.loc.noCoord'))
        : null,
    prov: null,
    checked_at: null,
    unit: 'm',
  };
}

/**
 * G6 호재 위치 확인 (D11-5, 계약 .8 PATCH /catalysts/{id} → CatalystUpdated {catalyst, links, job}) — catalyst_link 는
 * 사람이 위치를 확인할 때만 생긴다(location_confirmed=false 면 링크 없음, RA). 영향 생활권·단지를 하나 이상 고르면
 * (좌표 lat·lon·예상 시기 expected_ym 은 선택 — D11-11 사람 입력만) 서버가 링크를 만들고, 단지 좌표가 없으면
 * distance_m=null·weight=1·라벨 추정·reason(연결 근거). 연결이 바뀌면 202 + 응답 job_id(snapshot.publish)를 감시한다(계약 .11 F3).
 * 판단(호재 단계)은 판정기 몫 — 여기서는 위치만.
 * '호재 아님'(D11-2) 은 목록에서 회색 배지로만 보인다(링크 대상 아님).
 */
export function CatalystLocationPanel({
  market,
  snapshotId,
  result,
  onResult,
}: {
  market: Market;
  snapshotId: string | null;
  /**
   * 마지막 저장 응답(연결 표·발행 잡). 화면(MarketPage)이 들고 있다 — 발행이 끝나 기본 리비전이 바뀌면 시장을 새로
   * 받는 동안 이 패널이 내려갔다 다시 올라오므로(7차 M7: 다른 리비전 값은 두지 않는다) 여기 두면 잡 진행이 사라진다.
   */
  result: CatalystUpdated | null;
  onResult: (result: CatalystUpdated) => void;
}) {
  const [openId, setOpenId] = useState<number | null>(null);
  const complexes = useComplexes(snapshotId, { page: 1, size: 1000, sort: 'name' });
  const names = new Map((complexes.data?.items ?? []).map((c) => [c.complex_id, c.name]));
  const catalysts = market.catalysts;
  return (
    <Section title={t('page.G6.loc.title')}>
      <p className="text-xs text-muted">{t('page.G6.loc.intro')}</p>
      {catalysts.length === 0 ? (
        <p className="text-sm text-muted">{t('page.G6.loc.none')}</p>
      ) : (
        <ul aria-label={t('page.G6.loc.title')} className="flex flex-col gap-2">
          {catalysts.map((c) => (
            <CatalystRow
              key={c.id}
              catalyst={c}
              open={openId === c.id}
              onToggle={() => setOpenId(openId === c.id ? null : c.id)}
              market={market}
              complexes={complexes.data?.items ?? []}
              onSaved={(patched) => {
                onResult(patched);
                setOpenId(null);
              }}
            />
          ))}
        </ul>
      )}
      {result ? <LinksTable result={result} names={names} areas={market.living_areas} /> : null}
    </Section>
  );
}

function CatalystRow({
  catalyst,
  open,
  onToggle,
  market,
  complexes,
  onSaved,
}: {
  catalyst: CatalystView;
  open: boolean;
  onToggle: () => void;
  market: Market;
  complexes: { complex_id: number; name: string }[];
  onSaved: (patched: CatalystUpdated) => void;
}) {
  const canWrite = useCanWrite();
  const update = useUpdateCatalystLocation();
  const notCatalyst = (catalyst.stage as string) === '호재 아님';
  const unconfirm = () =>
    update.mutate(
      { id: catalyst.id, patch: { location_confirmed: false } },
      { onSuccess: onSaved },
    );
  return (
    <li className="flex flex-col gap-1 border-b border-border pb-2" data-catalyst-id={catalyst.id}>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-medium">{catalyst.name}</span>
        <Badge tone={notCatalyst ? 'muted' : 'neutral'}>
          {enumText('chart.C09.stage', catalyst.stage)}
        </Badge>
        <Badge tone={catalyst.location_confirmed ? 'strong' : 'muted'} data-testid="loc-status">
          {catalyst.location_confirmed ? t('page.G6.loc.confirmed') : t('page.G6.loc.unconfirmed')}
        </Badge>
        {!notCatalyst ? (
          <span className="ml-auto flex gap-2" data-write>
            <button
              type="button"
              onClick={onToggle}
              disabled={!canWrite}
              title={canWrite ? undefined : t('auth.readOnlyHint')}
              aria-expanded={open}
              className="rounded-sm border border-border px-2 py-0.5 text-xs disabled:opacity-50"
            >
              {t('page.G6.loc.open')}
            </button>
            {catalyst.location_confirmed ? (
              <button
                type="button"
                onClick={unconfirm}
                disabled={!canWrite || update.isPending}
                className="rounded-sm border border-border px-2 py-0.5 text-xs disabled:opacity-50"
              >
                {t('page.G6.loc.unconfirm')}
              </button>
            ) : null}
          </span>
        ) : null}
      </div>
      {open ? (
        <LocationForm
          catalyst={catalyst}
          market={market}
          complexes={complexes}
          pending={update.isPending}
          serverError={
            update.error instanceof ApiError ? update.error.detail : (update.error?.message ?? null)
          }
          onSubmit={(patch) => update.mutate({ id: catalyst.id, patch }, { onSuccess: onSaved })}
        />
      ) : null}
    </li>
  );
}

function LocationForm({
  catalyst,
  market,
  complexes,
  pending,
  serverError,
  onSubmit,
}: {
  catalyst: CatalystView;
  market: Market;
  complexes: { complex_id: number; name: string }[];
  pending: boolean;
  serverError: string | null;
  onSubmit: (patch: CatalystPatch) => void;
}) {
  const baseId = useId();
  const [lat, setLat] = useState('');
  const [lon, setLon] = useState('');
  const [ym, setYm] = useState('');
  const [areas, setAreas] = useState<string[]>([]);
  const [complexIds, setComplexIds] = useState<number[]>(catalyst.linked_complex_ids ?? []);
  const [error, setError] = useState<string | null>(null);

  const submit = () => {
    const la = parseCoord(lat, 'lat');
    const lo = parseCoord(lon, 'lon');
    if (la === 'invalid' || lo === 'invalid') {
      setError(t('page.G6.loc.badCoord'));
      return;
    }
    if ((la === null) !== (lo === null)) {
      setError(t('page.G6.loc.bothCoord'));
      return;
    }
    const expected = parseYm(ym);
    if (expected === 'invalid') {
      setError(t('page.G6.loc.badYm'));
      return;
    }
    // 서버: 영향 범위(생활권·단지) 없이 location_confirmed=true 는 422 — 좌표만으로는 연결을 만들지 않는다
    if (areas.length === 0 && complexIds.length === 0) {
      setError(t('page.G6.loc.needTarget'));
      return;
    }
    setError(null);
    onSubmit({
      location_confirmed: true,
      ...(la !== null && lo !== null ? { lat: la, lon: lo } : {}),
      ...(expected !== null ? { expected_ym: expected } : {}),
      living_area_ids: areas,
      complex_ids: complexIds,
    });
  };

  return (
    <form
      aria-label={t('page.G6.loc.formFor', { name: catalyst.name })}
      noValidate
      data-write
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
      className="grid gap-2 rounded-sm border border-border p-2 text-sm sm:grid-cols-2"
    >
      <label className="flex flex-col gap-0.5" htmlFor={`${baseId}-lat`}>
        <span className="text-xs text-muted">{t('page.G6.loc.lat')}</span>
        <input
          id={`${baseId}-lat`}
          inputMode="decimal"
          value={lat}
          onChange={(e) => setLat(e.target.value)}
          className={inputClass}
        />
      </label>
      <label className="flex flex-col gap-0.5" htmlFor={`${baseId}-lon`}>
        <span className="text-xs text-muted">{t('page.G6.loc.lon')}</span>
        <input
          id={`${baseId}-lon`}
          inputMode="decimal"
          value={lon}
          onChange={(e) => setLon(e.target.value)}
          className={inputClass}
        />
      </label>
      <label className="flex flex-col gap-0.5" htmlFor={`${baseId}-ym`}>
        <span className="text-xs text-muted">{t('page.G6.loc.expectedYm')}</span>
        <input
          id={`${baseId}-ym`}
          type="month"
          value={ym}
          onChange={(e) => setYm(e.target.value)}
          className={inputClass}
        />
      </label>
      <fieldset className="flex flex-col gap-0.5">
        <legend className="text-xs text-muted">{t('page.G6.loc.areas')}</legend>
        <div className="flex flex-wrap gap-2">
          {market.living_areas.map((la) => (
            <label key={la.id} className="inline-flex items-center gap-1 text-xs">
              <input
                type="checkbox"
                checked={areas.includes(la.id)}
                onChange={(e) =>
                  setAreas(e.target.checked ? [...areas, la.id] : areas.filter((x) => x !== la.id))
                }
              />
              {la.name}
            </label>
          ))}
        </div>
      </fieldset>
      <label className="flex flex-col gap-0.5" htmlFor={`${baseId}-cx`}>
        <span className="text-xs text-muted">{t('page.G6.loc.complexes')}</span>
        <select
          id={`${baseId}-cx`}
          multiple
          size={4}
          value={complexIds.map(String)}
          onChange={(e) => setComplexIds([...e.target.selectedOptions].map((o) => Number(o.value)))}
          className={inputClass}
        >
          {complexes.map((c) => (
            <option key={c.complex_id} value={c.complex_id}>
              {c.name}
            </option>
          ))}
        </select>
      </label>
      <div className="flex flex-wrap items-center gap-2 sm:col-span-2">
        <button
          type="submit"
          disabled={pending}
          className="rounded-sm bg-accent px-3 py-1 text-sm text-accent-fg disabled:opacity-50"
        >
          {t('page.G6.loc.submit')}
        </button>
        {(error ?? serverError) ? (
          <p role="alert" className="text-sm text-danger">
            {error ?? t('page.common.loadError', { detail: serverError ?? '' })}
          </p>
        ) : null}
      </div>
    </form>
  );
}

/** 계약 .11 F3: 감시할 잡 = `job_id`(snapshot.publish). 옛 응답(job_id 없음)이면 job.id */
export function jobIdOf(result: Pick<CatalystUpdated, 'job' | 'job_id'>): number | null {
  return result.job_id ?? result.job?.id ?? null;
}

/**
 * 저장 결과: 만들어진 catalyst_link(단지·거리·가중치·근거) + 보이는 값(위치·좌표·예정월·연결)이 바뀌었으면 새 리비전 발행
 * 잡(202 + job_id, 계약 .13 F3·D16-4) 진행. 바뀐 것이 없으면 200 + job_id null — "바뀐 것 없음"만 보인다.
 * 잡이 끝날 때까지 이전 발행 리비전이 기본 화면이다.
 */
function LinksTable({
  result,
  names,
  areas,
}: {
  result: CatalystUpdated;
  names: Map<number, string>;
  areas: readonly LivingAreaRef[];
}) {
  return (
    <div className="flex flex-col gap-2">
      <LinksBody result={result} names={names} areas={areas} />
      {jobIdOf(result) !== null ? (
        <div data-testid="catalyst-job">
          <p className="text-xs text-muted">{t('page.G6.loc.jobHint')}</p>
          <PublishJobProgress jobId={jobIdOf(result) as number} />
        </div>
      ) : (
        // 계약 .13 F3(D16-4): 200 = 바뀐 것 없음 — 진행 안내·잡 감시 없이 끝
        <p className="text-xs text-muted" data-testid="catalyst-job-none">
          {t('page.G6.loc.unchanged')}
        </p>
      )}
    </div>
  );
}

function LinksBody({
  result,
  names,
  areas,
}: {
  result: CatalystUpdated;
  names: Map<number, string>;
  areas: readonly LivingAreaRef[];
}) {
  const caption = t('page.G6.loc.links', { name: result.catalyst.name });
  if (result.links.length === 0) {
    return (
      <p role="status" className="text-sm text-muted" data-testid="catalyst-links">
        {result.catalyst.location_confirmed ? t('page.G6.loc.noLinks') : t('page.G6.loc.cleared')}
      </p>
    );
  }
  return (
    <table
      aria-label={caption}
      className="w-full border-collapse text-sm"
      data-testid="catalyst-links"
    >
      <caption className="text-left text-xs text-muted">{caption}</caption>
      <thead>
        <tr>
          <th scope="col" className={thClass}>
            {t('page.G6.loc.col.complex')}
          </th>
          <th scope="col" className={thClass}>
            {t('page.G6.loc.col.distance')}
          </th>
          <th scope="col" className={thClass}>
            {t('page.G6.loc.col.weight')}
          </th>
          <th scope="col" className={thClass}>
            {t('page.G6.loc.col.reason')}
          </th>
        </tr>
      </thead>
      <tbody>
        {result.links.map((link) => (
          <tr key={link.complex_id}>
            <th scope="row" className={`${tdClass} text-left font-normal`}>
              {names.get(link.complex_id) ?? t('page.G6.loc.unknownComplex')}
            </th>
            <td className={tdClass}>
              <FactCell fact={distanceFact(link, areas)} unit="m" />
            </td>
            <td className={tdClass}>
              {/* 가중치 = 거리·생활권에서 정한 계산 계수(사실 아님). null = 서버가 정하지 않음 */}
              {link.weight === null ? (
                <span className="text-muted">{t('page.common.none')}</span>
              ) : (
                <MetaValue kind="derived" value={link.weight} as="number" digits={2} />
              )}
            </td>
            <td className={`${tdClass} text-xs`}>
              {livingAreaReason(link.reason, areas) ?? t('page.common.none')}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

const inputClass = 'w-full rounded-sm border border-border bg-surface px-2 py-1 text-sm';
