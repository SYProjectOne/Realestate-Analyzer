/**
 * R9-UI P6(30-proposal §7, D28-4): 용어 — Term(ⓘ 팝오버) · /glossary · 헤더 '용어' 링크.
 * 문구는 ko.json glossary.items 에서만 오고, 제도 수치·권유어를 넣지 않는다. 정보를 더하기만 한다.
 */
import { cleanup, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import ko from '@/i18n/ko.json';
import { t } from '@/i18n';
import { forbiddenIn } from '@/test/forbidden';
import { MOBILE_QUERY } from '@/lib/useMediaQuery';
import { resetMockState } from '@/mocks/handlers.extra';
import { renderRoute, renderWithProviders } from '@/test/render';
import { Term, GLOSSARY_KEYS, type GlossaryKey } from '@/components';

vi.mock('@/charts/EChartRuntime', () => ({ default: () => null }));
beforeEach(() => resetMockState());

describe('glossary.items 문구', () => {
  it('모든 항목에 term·short 가 있고 분류가 정해진 값', () => {
    const cats = Object.keys(ko.glossary.category);
    for (const [key, item] of Object.entries(ko.glossary.items)) {
      expect({ key, term: item.term.trim().length > 0 }).toEqual({ key, term: true });
      expect({ key, short: item.short.trim().length > 0 }).toEqual({ key, short: true });
      expect(cats).toContain(item.cat);
      expect({ key, words: forbiddenIn(item.term + item.short) }).toEqual({ key, words: [] });
    }
  });

  it('검수 결과 반영(30-proposal §7-3): 확인 안 된 제도 수치·권유어를 넣지 않았다', () => {
    const all = JSON.stringify(ko.glossary);
    expect(all).not.toContain('84점');
    expect(all).not.toContain('만 30세');
    expect(all).not.toContain('기회');
    expect(ko.glossary.items.lottery.short).toContain('가점과 관계없이');
    expect(ko.glossary.items.points.short).toContain('이 앱은 가점을 계산하지 않습니다');
    // 가격 갭 정의는 RA §6-2(중앙값·생활권·2020년 이후·80~85㎡·6개월)
    for (const word of ['중앙값', '생활권', '2020년', '80~85㎡', '6개월']) {
      expect(ko.glossary.items.gap.short).toContain(word);
    }
    // +10% 는 목표 시점을 고정하지 않고, 당첨 확률이 아님을 밝힌다
    expect(ko.glossary.items.p10.short).not.toContain('입주 1년');
    expect(ko.glossary.items.p10.short).toContain('당첨 확률이 아니고');
    expect(ko.glossary.items.intake_status.short).toContain('판정기');
  });

  it('GLOSSARY_KEYS = ko.json 항목 키(화면이 쓰는 key 는 타입 GlossaryKey)', () => {
    expect([...GLOSSARY_KEYS].sort()).toEqual(Object.keys(ko.glossary.items).sort());
    const k: GlossaryKey = 'resale_end';
    expect(GLOSSARY_KEYS).toContain(k);
  });
});

describe('Term(ⓘ)', () => {
  it('버튼 aria-expanded·aria-controls, 팝오버에 한 줄 정의와 용어 모음 링크, Esc 로 닫힘', async () => {
    renderWithProviders(
      <MemoryRouter>
        <Term k="resale_end">{t('page.G3.header.resaleEnd')}</Term>
      </MemoryRouter>,
    );
    const button = screen.getByRole('button', {
      name: t('glossary.open', { term: ko.glossary.items.resale_end.term }),
    });
    expect(button).toHaveAttribute('aria-expanded', 'false');
    await userEvent.click(button);
    expect(button).toHaveAttribute('aria-expanded', 'true');
    const pop = document.getElementById(button.getAttribute('aria-controls') ?? '') as HTMLElement;
    expect(pop).not.toBeNull();
    expect(pop).toHaveTextContent(ko.glossary.items.resale_end.short);
    expect(within(pop).getByRole('link', { name: t('glossary.more') })).toHaveAttribute(
      'href',
      expect.stringMatching(/\/glossary.*#resale_end$/),
    );
    await userEvent.keyboard('{Escape}');
    expect(button).toHaveAttribute('aria-expanded', 'false');
  });
});

describe('/glossary 용어 모음', () => {
  it('제목·안내·분류·검색 — 검색하면 맞는 항목만', async () => {
    renderRoute('/glossary');
    expect(
      await screen.findByRole('heading', { level: 1, name: t('glossary.title') }),
    ).toBeInTheDocument();
    expect(screen.getByText(t('glossary.intro'))).toBeInTheDocument();
    const list = screen.getByRole('list', { name: t('glossary.title') });
    const total = within(list).getAllByRole('listitem').length;
    expect(total).toBeGreaterThanOrEqual(Object.keys(ko.glossary.items).length);
    await userEvent.type(screen.getByRole('searchbox', { name: t('glossary.search') }), '전매');
    const hits = within(list).getAllByRole('listitem');
    expect(hits.length).toBeGreaterThan(0);
    expect(hits.length).toBeLessThan(total);
    for (const hit of hits) expect(hit).toHaveTextContent('전매');
    // 라벨 분류는 라벨 뜻(label.help) 그대로
    await userEvent.clear(screen.getByRole('searchbox', { name: t('glossary.search') }));
    await userEvent.click(screen.getByRole('button', { name: t('glossary.category.labels') }));
    expect(within(list).getByText(t('label.help.unknown'))).toBeInTheDocument();
  });

  it('헤더에 "용어" 링크, 모바일에서도 읽기 전용으로 열린다', async () => {
    renderRoute('/');
    const nav = await screen.findByRole('link', { name: t('glossary.nav') });
    expect(nav.getAttribute('href')).toMatch(/^\/glossary/);
    cleanup();
    const original = window.matchMedia;
    window.matchMedia = ((query: string) => ({
      ...original(query),
      matches: query === MOBILE_QUERY,
    })) as typeof window.matchMedia;
    try {
      renderRoute('/glossary');
      expect(
        await screen.findByRole('heading', { level: 1, name: t('glossary.title') }),
      ).toBeInTheDocument();
      expect(screen.getByText(t('app.mobileReadOnly'))).toBeInTheDocument();
    } finally {
      window.matchMedia = original;
    }
  });
});

describe('같은 화면에서 같은 용어 ⓘ 는 한 번(30-proposal §7-1)', () => {
  it.each([
    ['/', 'G1'],
    ['/complexes', 'G2'],
    ['/complexes/2', 'G3'],
  ])('%s', async (path) => {
    const { container } = renderRoute(path);
    await screen.findByRole('heading', { level: 1 });
    await screen.findAllByTestId('term');
    const keys = [...container.querySelectorAll('[data-testid="term"]')].map((el) =>
      el.getAttribute('data-term'),
    );
    expect(keys.length).toBeGreaterThan(0);
    expect(new Set(keys).size).toBe(keys.length);
  });
});
