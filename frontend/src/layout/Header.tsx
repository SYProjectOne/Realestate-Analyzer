import { Link, NavLink, useLocation, useNavigate } from 'react-router';
import { usePendingWatchExpired, useScenarios } from '@/api/hooks';
import { TokenButton } from '@/app/TokenDialog';
import { RegionPicker, ScenarioToggle, SnapshotPicker } from '@/components';
import { useActiveRegion } from '@/hooks/useActiveRegion';
import { scenarioKey, useScenario } from '@/hooks/useScenario';
import { useSnapshot } from '@/hooks/useSnapshot';
import { t, type TKey } from '@/i18n';
import { useIsMobile } from '@/lib/useMediaQuery';
import { ThemeToggle } from './ThemeToggle';

export interface NavItem {
  to: string;
  key: TKey;
  end?: boolean;
}

/**
 * 메뉴(D30-2, R9-UI 결정 12(a), D28-4): 초보가 쓰는 화면을 앞에 — 홈·단지 찾기·비교하기·지역 시장·보고서 │
 * 내 조건(시나리오)·데이터·운영(옆, 작게) · 용어 사전(오른쪽 끝). 숨기지는 않는다. 라우트 경로는 그대로(D30-2).
 * 모바일(≤768px)은 머리줄에 메뉴를 두지 않고 하단 고정 바(BottomNav, D30-4) 3개.
 */
export const NAV_MAIN: NavItem[] = [
  { to: '/', key: 'nav.G1', end: true },
  { to: '/complexes', key: 'nav.G2' },
  { to: '/compare', key: 'nav.G4' },
  { to: '/market', key: 'nav.G6' },
  { to: '/reports', key: 'nav.G8' },
];
export const NAV_SIDE: NavItem[] = [
  { to: '/scenario', key: 'nav.G5' },
  { to: '/ops', key: 'nav.G7' },
];
export const GLOSSARY: NavItem = { to: '/glossary', key: 'glossary.nav' };

/** 앱 표지(집 모양) — 장식. 이름은 글자로 */
export function LogoMark({ size = 32 }: { size?: number }) {
  return (
    <span
      aria-hidden
      style={{ width: size, height: size }}
      className="inline-flex shrink-0 items-center justify-center rounded-[9px] bg-accent text-accent-fg"
    >
      <svg
        width={Math.round(size * 0.56)}
        height={Math.round(size * 0.56)}
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M3 21h18" />
        <path d="M5 21V9l7-5 7 5v12" />
        <path d="M10 21v-6h4v6" />
      </svg>
    </span>
  );
}

const linkBase =
  'whitespace-nowrap rounded-full focus:outline-hidden focus-visible:ring-2 focus-visible:ring-accent';

/**
 * 전역 머리줄(D30-2, 목업 Shell 머리줄): 윗줄 = 표지·앱 이름(홈 링크)·메뉴·용어 사전,
 * 아랫줄 = 지역(+지역 추가)·기준일·상황 + 접속 열쇠·화면 밝기. 선택은 URL 쿼리로 공유되고 메뉴 이동에도 따라간다.
 * 휴대폰: 메뉴는 하단 바, 아랫줄은 고르기 칸 + 접힌 '설정'(열쇠·화면) — 첫 줄에서 열쇠를 먼저 읽지 않게(R9-UI P5).
 */
export function Header() {
  const navigate = useNavigate();
  const location = useLocation();
  const isMobile = useIsMobile();
  const { regions, region, setRegion } = useActiveRegion();
  const { snapshots, snapshotId, setSnapshot } = useSnapshot();
  const { scenarioId, setScenario } = useScenario();
  const { data: scenarios = [] } = useScenarios();
  // 7차 minor 21: 발행 대기 리비전 감시가 30분 상한에서 멈추면 알리고 다시 확인할 수 있게 한다
  const watch = usePendingWatchExpired(region?.id);
  const options = scenarios.map((s) => ({ id: scenarioKey(s), name: s.name }));
  const selected = scenarioId ?? (options[0] ? String(options[0].id) : '');

  const link = (item: NavItem, variant: 'main' | 'side' | 'glossary') => (
    <NavLink
      key={item.to}
      to={{ pathname: item.to, search: location.search }}
      end={item.end}
      className={({ isActive }) => {
        if (variant === 'glossary') {
          return `whitespace-nowrap rounded-[10px] border px-3 py-2 text-sm focus:outline-hidden focus-visible:ring-2 focus-visible:ring-accent ${
            isActive
              ? 'border-transparent bg-accent-soft font-semibold text-accent-ink'
              : 'border-border-strong text-fg-2 hover:text-fg'
          }`;
        }
        const size = variant === 'side' ? 'px-2.5 py-1.5 text-[13px]' : 'px-3.5 py-2 text-[15px]';
        return `${linkBase} ${size} ${
          isActive
            ? 'bg-accent-soft font-semibold text-accent-ink'
            : variant === 'side'
              ? 'text-muted hover:bg-chip hover:text-fg'
              : 'font-medium text-fg-2 hover:bg-chip hover:text-fg'
        }`;
      }}
    >
      {t(item.key)}
    </NavLink>
  );

  return (
    <header
      className="sticky top-0 z-30 border-b border-border bg-surface"
      data-testid="app-header"
    >
      <div className="mx-auto flex max-w-[1280px] flex-wrap items-center gap-x-6 gap-y-3 px-4 py-3 sm:px-6">
        <Link
          to={{ pathname: '/', search: location.search }}
          className="flex items-center gap-2.5 text-lg font-bold text-fg focus:outline-hidden focus-visible:ring-2 focus-visible:ring-accent"
          data-testid="app-home"
        >
          <LogoMark size={isMobile ? 26 : 32} />
          {t('app.name')}
        </Link>
        {isMobile ? null : (
          <nav
            aria-label={t('nav.label')}
            className="flex min-w-0 flex-1 flex-wrap items-center gap-1"
          >
            {NAV_MAIN.map((item) => link(item, 'main'))}
            <span aria-hidden className="mx-1.5 h-5 w-px bg-border-strong" />
            {NAV_SIDE.map((item) => link(item, 'side'))}
            <span className="ml-auto">{link(GLOSSARY, 'glossary')}</span>
          </nav>
        )}
      </div>
      <div className="border-t border-border bg-surface-2">
        <div
          role="group"
          aria-label={t('header.selectors')}
          className="mx-auto flex max-w-[1280px] flex-wrap items-center gap-x-5 gap-y-2.5 px-4 py-2.5 sm:px-6"
        >
          <RegionPicker
            regions={regions}
            value={region ? String(region.id) : null}
            onChange={setRegion}
            onAddRegion={() => navigate('/regions/new')}
          />
          <SnapshotPicker snapshots={snapshots} value={snapshotId} onChange={setSnapshot} />
          {isMobile ? (
            // R9-UI P5: 모바일은 잘리는 토글 대신 select(전체 이름)
            <label className="flex items-center gap-2 text-sm">
              <span className="text-[13px] text-muted">{t('header.scenario')}</span>
              <select
                aria-label={t('header.scenario')}
                value={selected}
                onChange={(e) => setScenario(e.target.value)}
                className="min-h-10 w-48 max-w-full rounded-[10px] border border-border-strong bg-surface px-2.5 py-1.5 text-sm font-semibold text-fg"
              >
                {options.map((o) => (
                  <option key={o.id} value={String(o.id)}>
                    {o.name}
                  </option>
                ))}
              </select>
            </label>
          ) : (
            /* 자리를 미리 잡아 둔다: 시나리오가 늦게 와도 본문이 밀리지 않게(CLS) */
            <span className="inline-flex h-11 max-w-full items-center overflow-x-auto">
              {scenarios.length > 0 ? (
                <ScenarioToggle
                  options={options}
                  value={scenarioId}
                  onChange={setScenario}
                  showLabel
                />
              ) : (
                <span
                  aria-hidden
                  className="inline-block h-10 w-xl max-w-full rounded-xl bg-chip"
                />
              )}
            </span>
          )}
          {isMobile ? (
            // R9-UI P5·SH-19: 토큰·테마는 접힌 '설정' 안(모바일 첫 줄에서 열쇠를 먼저 읽지 않게)
            <details className="w-full rounded-[10px] border border-border bg-surface px-2.5 py-1.5 text-[13px]">
              <summary className="min-h-7 cursor-pointer font-semibold text-fg-2">
                {t('header.settings')}
              </summary>
              <span className="mt-1.5 flex flex-wrap items-center gap-1.5">
                <TokenButton />
                <ThemeToggle />
              </span>
            </details>
          ) : (
            <span className="ml-auto flex items-center gap-2">
              <TokenButton />
              <ThemeToggle />
            </span>
          )}
        </div>
      </div>
      {watch.expired ? (
        <div className="border-t border-border bg-subtle">
          <p
            role="status"
            data-testid="publish-watch-expired"
            className="mx-auto flex max-w-[1280px] flex-wrap items-center gap-x-3 gap-y-1.5 px-4 py-2 text-[13px] text-fg-2 sm:px-6"
          >
            <span className="flex-[1_1_320px]">{t('job.watchExpired')}</span>
            <button
              type="button"
              onClick={watch.recheck}
              className="min-h-9 rounded-[10px] border border-border-strong bg-surface px-3 text-[13px] font-semibold text-fg"
            >
              {t('job.watchRecheck')}
            </button>
          </p>
        </div>
      ) : null}
    </header>
  );
}
