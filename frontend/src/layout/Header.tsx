import { NavLink, useLocation, useNavigate } from 'react-router';
import { usePendingWatchExpired, useScenarios } from '@/api/hooks';
import { TokenButton } from '@/app/TokenDialog';
import { RegionPicker, ScenarioToggle, SnapshotPicker } from '@/components';
import { useActiveRegion } from '@/hooks/useActiveRegion';
import { scenarioKey, useScenario } from '@/hooks/useScenario';
import { useSnapshot } from '@/hooks/useSnapshot';
import { t, type TKey } from '@/i18n';
import { useIsMobile } from '@/lib/useMediaQuery';
import { ThemeToggle } from './ThemeToggle';

interface NavItem {
  to: string;
  key: TKey;
  end?: boolean;
}

/**
 * 메뉴(R9-UI 결정 12(a), D28-4): 초보가 쓰는 화면을 앞에 — 홈·단지 리스트·비교·지역 시장·보고서 │ 시나리오·데이터·운영(옆, 작게).
 * 숨기지는 않는다. 모바일(≤768px)은 D7 읽기 전용 지원 화면(홈·단지 리스트)만 + 용어 모음.
 */
const NAV_MAIN: NavItem[] = [
  { to: '/', key: 'nav.G1', end: true },
  { to: '/complexes', key: 'nav.G2' },
  { to: '/compare', key: 'nav.G4' },
  { to: '/market', key: 'nav.G6' },
  { to: '/reports', key: 'nav.G8' },
];
const NAV_SIDE: NavItem[] = [
  { to: '/scenario', key: 'nav.G5' },
  { to: '/ops', key: 'nav.G7' },
];
const NAV_MOBILE: NavItem[] = [
  { to: '/', key: 'nav.G1', end: true },
  { to: '/complexes', key: 'nav.G2' },
];
const GLOSSARY: NavItem = { to: '/glossary', key: 'glossary.nav' };

/** 전역 헤더: 지역(+지역 추가)·기준일·상황 토글·테마 + 화면 탭. 선택은 URL 쿼리로 공유된다. */
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

  const link = (item: NavItem, small = false) => (
    <NavLink
      key={item.to}
      to={{ pathname: item.to, search: location.search }}
      end={item.end}
      className={({ isActive }) =>
        `whitespace-nowrap rounded-sm px-2 py-1 ${small ? 'text-xs' : ''} ${isActive ? 'bg-accent text-accent-fg' : 'text-muted hover:text-fg'}`
      }
    >
      {t(item.key)}
    </NavLink>
  );

  return (
    <header className="sticky top-0 z-30 border-b border-border bg-surface/95 backdrop-blur-sm">
      <div className="mx-auto flex max-w-(--breakpoint-2xl) flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2">
        <span className="font-semibold">{t('app.name')}</span>
        <RegionPicker
          regions={regions}
          value={region ? String(region.id) : null}
          onChange={setRegion}
          onAddRegion={() => navigate('/regions/new')}
        />
        <SnapshotPicker snapshots={snapshots} value={snapshotId} onChange={setSnapshot} />
        {isMobile ? (
          // R9-UI P5: 모바일은 잘리는 토글 대신 select(전체 이름)
          <label className="flex items-center gap-1 text-sm">
            <span className="text-muted">{t('header.scenario')}</span>
            <select
              aria-label={t('header.scenario')}
              value={selected}
              onChange={(e) => setScenario(e.target.value)}
              className="w-48 max-w-full rounded-sm border border-border bg-surface px-2 py-1 text-sm"
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
          <span className="inline-flex h-[30px] max-w-full overflow-x-auto">
            {scenarios.length > 0 ? (
              <ScenarioToggle options={options} value={scenarioId} onChange={setScenario} />
            ) : (
              <span aria-hidden className="inline-block w-xl max-w-full" />
            )}
          </span>
        )}
        {isMobile ? (
          // R9-UI P5: 토큰·테마는 접힌 '설정' 안(모바일 첫 줄에서 'API 토큰'을 먼저 읽지 않게)
          <details className="ml-auto text-sm">
            <summary className="cursor-pointer text-muted">{t('header.settings')}</summary>
            <span className="mt-1 flex items-center gap-2">
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
      {watch.expired ? (
        <p
          role="status"
          data-testid="publish-watch-expired"
          className="mx-auto flex max-w-(--breakpoint-2xl) flex-wrap items-center gap-2 px-4 pb-1 text-xs text-muted"
        >
          <span>{t('job.watchExpired')}</span>
          <button type="button" onClick={watch.recheck} className="underline">
            {t('job.watchRecheck')}
          </button>
        </p>
      ) : null}
      <nav className="mx-auto flex max-w-(--breakpoint-2xl) items-center gap-1 overflow-x-auto px-4 pb-1 text-sm">
        {isMobile ? (
          <>
            {NAV_MOBILE.map((item) => link(item))}
            <span className="ml-auto">{link(GLOSSARY)}</span>
          </>
        ) : (
          <>
            {NAV_MAIN.map((item) => link(item))}
            <span aria-hidden className="mx-1 h-4 w-px bg-border" />
            {NAV_SIDE.map((item) => link(item, true))}
            <span className="ml-auto">{link(GLOSSARY)}</span>
          </>
        )}
      </nav>
    </header>
  );
}
