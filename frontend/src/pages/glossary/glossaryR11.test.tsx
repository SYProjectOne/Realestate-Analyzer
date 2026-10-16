/**
 * R11 용어 사전(목업 Glossary 보드, 고침 GL-1~GL-6): 질문형 카드 · 개수 붙은 분류 칩 · 분류와 찾는 말 함께 거르기(AND) ·
 * 개수 줄 · 결과 없음 · #key 강조 · 라벨 카드 = 라벨 뜻 원본. 대응표 coverage-Glossary.md '테스트' 칸이 이 이름을 가리킨다.
 */
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { t } from '@/i18n';
import ko from '@/i18n/ko.json';
import { renderRoute } from '@/test/render';
import source from './index.tsx?raw';
import { CATEGORIES, filterGlossary, glossaryEntries } from './index';

vi.mock('@/charts/EChartRuntime', () => ({ default: () => null }));

const ITEM_COUNT = Object.keys(ko.glossary.items).length;
const LABEL_COUNT = Object.keys(ko.label.help).length;

describe('용어 54개 데이터(ko.json 만)', () => {
  it('항목 48 + 라벨 6 = 54, ko.json 순서(청약 기본 → 자격·순위 → 제한 → 돈 → 계산값) 뒤에 라벨', () => {
    const all = glossaryEntries();
    expect(ITEM_COUNT + LABEL_COUNT).toBe(54);
    expect(all).toHaveLength(54);
    expect(all.map((e) => e.key).slice(0, ITEM_COUNT)).toEqual(Object.keys(ko.glossary.items));
    expect(all.slice(ITEM_COUNT).every((e) => e.cat === 'labels')).toBe(true);
    const firstOf = (cat: string) => all.findIndex((e) => e.cat === cat);
    expect(firstOf('basic')).toBeLessThan(firstOf('who'));
    expect(firstOf('who')).toBeLessThan(firstOf('limits'));
    expect(firstOf('limits')).toBeLessThan(firstOf('money'));
    expect(firstOf('money')).toBeLessThan(firstOf('app'));
  });

  it('모든 카드 제목은 질문형(…이란?/…란?) ko 문구 그대로', () => {
    for (const e of glossaryEntries()) {
      expect({ key: e.key, q: /(이란|란)\?$/.test(e.q) }).toEqual({ key: e.key, q: true });
    }
    expect(ko.glossary.items.resale_limit.q).toBe('전매제한이란?');
    expect(ko.glossary.labelQ.human).toBe('사람 확인됨이란?');
  });

  it('라벨 카드 6장 = 출처 범례 라벨 뜻(label.help) 한 원본(GL-1·SH-1)', () => {
    const labels = glossaryEntries().filter((e) => e.cat === 'labels');
    expect(labels.map((e) => e.short)).toEqual(Object.values(ko.label.help));
    expect(labels.map((e) => e.term)).toEqual([
      '확인됨',
      '추정',
      '비공식',
      '재가공',
      '확인 불가',
      '사람 확인됨',
    ]);
    expect(ko.label.help.estimated).toContain('괄호 안이 계산 방법');
    expect(ko.label.help.unknown).toContain('괄호 안이 이유');
    expect(ko.label.help.unofficial).toContain('보도·블로그·홍보');
  });

  it('되살린 문장(GL-2·GL-3·GL-5): 확인된 할인만 · 목표 시점 · 배점 · 공고마다 · 거주의무 · 타입별 가격 탭 · 이유는 같은 줄', () => {
    const i = ko.glossary.items;
    expect(i.current_price.short).toContain('확인된 할인만');
    expect(i.current_price.short).toContain('최저가 층');
    expect(i.p10.q).toBe('가격 +10% 오를 가능성이란?');
    for (const w of [
      '기준일+3년',
      '기준일+5년',
      '화면에 함께 적어요',
      '당첨 확률이 아니고',
      '보장 아님',
    ]) {
      expect(i.p10.short).toContain(w);
    }
    expect(i.point_system.short).toContain('배점은 청약홈에서 확인하세요');
    expect(i.no_rank.short).toContain('자격·지역 요건은 공고마다');
    expect(i.arbitrary.short).toContain('조건은 공고마다');
    expect(i.first_come.short).toContain('조건은 공고마다');
    expect(i.reserve.short).toContain('순서대로 계약할');
    expect(i.residency.term).toContain('(거주의무)');
    expect(i.basis_type.short).toContain('타입별 가격 탭');
    expect(i.gap.short).toContain("3건보다 적으면 대체 단지를 쓰고 라벨이 '추정'");
    expect(i.judge_scope.q).toContain('(판정 범위)');
    expect(i.judge_scope.short).toContain('이유는 같은 줄');
  });

  it('분류 + 찾는 말 함께 거르기(AND, 앞뒤 빈칸 뺌): 제한 + "전매" → 4개', () => {
    const all = glossaryEntries();
    const hits = filterGlossary(all, 'limits', '  전매  ');
    expect(hits.map((e) => e.key)).toEqual([
      'resale_limit',
      'resale_end',
      'price_cap',
      'regulated',
    ]);
    expect(filterGlossary(all, null, '').length).toBe(54);
    expect(filterGlossary(all, 'labels', '전매')).toEqual([]);
  });

  it('서버를 부르지 않는다 — 화면 코드는 @/api 를 쓰지 않는다(#28)', () => {
    expect(source).not.toContain('@/api');
  });
});

describe('/glossary 화면(R11)', () => {
  it('분류 칩: 전체 · 청약 기본 · 자격·순위 · 돈 · 제한 · 이 앱의 계산값 · 라벨 + 개수, aria-pressed', async () => {
    renderRoute('/glossary');
    const group = await screen.findByRole('group', { name: t('glossary.categoryGroup') });
    const chips = within(group).getAllByRole('button');
    const all = glossaryEntries();
    const count = (c: string) => all.filter((e) => e.cat === c).length;
    expect(chips.map((c) => c.textContent)).toEqual([
      `${t('glossary.all')} 54`,
      ...CATEGORIES.map((c) => `${t(`glossary.category.${c}`)} ${count(c)}`),
    ]);
    expect(chips.map((c) => c.textContent)).toEqual([
      '전체 54',
      '청약 기본 4',
      '자격·순위 16',
      '돈 7',
      '제한 6',
      '이 앱의 계산값 15',
      '라벨 6',
    ]);
    expect(chips[0]).toHaveAttribute('aria-pressed', 'true');
  });

  it('분류 누르고 찾는 말 넣으면 함께 걸러지고, 개수 줄에 조건을 적는다', async () => {
    renderRoute('/glossary');
    const group = await screen.findByRole('group', { name: t('glossary.categoryGroup') });
    await userEvent.click(within(group).getByRole('button', { name: /^제한 / }));
    await userEvent.type(screen.getByRole('searchbox', { name: t('glossary.search') }), '전매');
    const list = screen.getByRole('list', { name: t('glossary.title') });
    expect(within(list).getAllByRole('article')).toHaveLength(4);
    expect(screen.getByTestId('glossary-count')).toHaveTextContent(
      t('glossary.countWith', {
        n: 4,
        cond: [
          t('glossary.condCategory', { name: t('glossary.category.limits') }),
          t('glossary.condQuery', { q: '전매' }),
        ].join(t('glossary.condJoin')),
      }),
    );
  });

  it('결과가 없으면 "찾는 용어가 없어요"(role=status)', async () => {
    renderRoute('/glossary');
    await userEvent.type(
      await screen.findByRole('searchbox', { name: t('glossary.search') }),
      '없는말없는말',
    );
    expect(t('glossary.none')).toBe('찾는 용어가 없어요');
    expect(screen.getByText(t('glossary.none'))).toHaveAttribute('role', 'status');
    expect(screen.getByTestId('glossary-count')).toHaveTextContent(
      t('glossary.countWith', { n: 0, cond: t('glossary.condQuery', { q: '없는말없는말' }) }),
    );
  });

  it('카드: h2 질문형 제목 + 분류 칩 + 풀이, id=term-{key}; #key 로 열면 그 카드 강조', async () => {
    renderRoute('/glossary#resale_limit');
    const card = await screen.findByRole('heading', {
      level: 2,
      name: ko.glossary.items.resale_limit.q,
    });
    const article = card.closest('article') as HTMLElement;
    expect(article).toHaveAttribute('id', 'term-resale_limit');
    expect(article).toHaveAttribute('data-target', 'true');
    expect(article).toHaveTextContent(t('glossary.category.limits'));
    expect(article).toHaveTextContent(ko.glossary.items.resale_limit.short);
    const other = screen
      .getByRole('heading', { level: 2, name: ko.glossary.items.rewin.q })
      .closest('article');
    expect(other).not.toHaveAttribute('data-target');
  });

  it('머리: 질문형 h1 + 개수 안내 + 검색칸 자리 글', async () => {
    renderRoute('/glossary');
    expect(
      await screen.findByRole('heading', { level: 1, name: t('glossary.heading') }),
    ).toBeInTheDocument();
    expect(screen.getByText(t('glossary.intro', { n: 54 }))).toBeInTheDocument();
    expect(screen.getByRole('searchbox', { name: t('glossary.search') })).toHaveAttribute(
      'placeholder',
      '예: 전매, 중도금, 특공',
    );
  });
});
