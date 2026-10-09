import { NavLink, useLocation, useNavigate } from 'react-router';
import { useScenarios } from '@/api/hooks';
import { TokenButton } from '@/app/TokenDialog';
import { RegionPicker, ScenarioToggle, SnapshotPicker } from '@/components';
import { useActiveRegion } from '@/hooks/useActiveRegion';
import { scenarioKey, useScenario } from '@/hooks/useScenario';
import { useSnapshot } from '@/hooks/useSnapshot';
import { t, type TKey } from '@/i18n';
import { ThemeToggle } from './ThemeToggle';

const NAV: { to: string; key: TKey; end?: boolean }[] = [
  { to: '/', key: 'nav.G1', end: true },
  { to: '/complexes', key: 'nav.G2' },
  { to: '/compare', key: 'nav.G4' },
  { to: '/scenario', key: 'nav.G5' },
  { to: '/market', key: 'nav.G6' },
  { to: '/ops', key: 'nav.G7' },
  { to: '/reports', key: 'nav.G8' },
];

/** 전역 헤더: 지역(+지역 추가)·기준일·상황 토글·테마 + 화면 탭. 선택은 URL 쿼리로 공유된다. */
export function Header() {
  const navigate = useNavigate();
  const location = useLocation();
  const { regions, region, setRegion } = useActiveRegion();
  const { snapshots, snapshotId, setSnapshot } = useSnapshot();
  const { scenarioId, setScenario } = useScenario();
  const { data: scenarios = [] } = useScenarios();

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
        {/* 자리를 미리 잡아 둔다: 시나리오가 늦게 와도 본문이 밀리지 않게(CLS) */}
        <span className="inline-flex h-[30px] max-w-full overflow-x-auto mobile:w-full">
          {scenarios.length > 0 ? (
            <ScenarioToggle
              options={scenarios.map((s) => ({ id: scenarioKey(s), name: s.name }))}
              value={scenarioId}
              onChange={setScenario}
            />
          ) : (
            <span aria-hidden className="inline-block w-xl max-w-full" />
          )}
        </span>
        <span className="ml-auto flex items-center gap-2">
          <TokenButton />
          <ThemeToggle />
        </span>
      </div>
      <nav className="mx-auto flex max-w-(--breakpoint-2xl) gap-1 overflow-x-auto px-4 pb-1 text-sm">
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            to={{ pathname: item.to, search: location.search }}
            end={item.end}
            className={({ isActive }) =>
              `whitespace-nowrap rounded-sm px-2 py-1 ${isActive ? 'bg-accent text-accent-fg' : 'text-muted hover:text-fg'}`
            }
          >
            {t(item.key)}
          </NavLink>
        ))}
      </nav>
    </header>
  );
}
