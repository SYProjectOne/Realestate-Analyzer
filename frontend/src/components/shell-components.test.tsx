/**
 * R11-SHELL 공통 부품(목업 Shell §3~§8) — 새 공용 부품(Card·StatusPill·SectionHeader·FactRow·BigNumber·KeepNote·Banner·
 * Skeleton)과 다시 그린 배지·라벨·빈 값·접수·작업 진행·표 토글·용어 '?'·라벨 뜻·출처 서랍·알림.
 * 대응표 coverage-Shell.md '테스트' 칸이 이 파일의 테스트 이름을 가리킨다.
 */
import { act, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { useEffect } from 'react';
import { MemoryRouter } from 'react-router';
import { ApiError } from '@/api/client';
import { ToastProvider, useToast, type ToastInput } from '@/app/toast';
import { provenanceConflict } from '@/charts/gallery/fixtures';
import { t } from '@/i18n';
import ko from '@/i18n/ko.json';
import type { Provenance } from '@/lib/contract';
import { MOBILE_QUERY } from '@/lib/useMediaQuery';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { QueryState } from '@/pages/_shared';
import { renderWithProviders } from '@/test/render';
import {
  Badge,
  Banner,
  BigNumber,
  CachedBadge,
  Card,
  DataTableToggle,
  EmptyState,
  FactCell,
  FactList,
  FactRow,
  IntakeBadge,
  JobProgressView,
  jobNameText,
  jobStepText,
  KeepNote,
  LabelBadge,
  MismatchBadge,
  ProvenanceLegend,
  SectionHeader,
  Skeleton,
  StatusPill,
  Term,
  TieBadge,
  UnstableBadge,
} from './index';

describe('공용 부품(R11 primitives)', () => {
  it('Card: 흰 카드(둥근 16px)·톤·요소·여백', () => {
    renderWithProviders(
      <>
        <Card data-testid="c1">본문</Card>
        <Card as="section" aria-label="구역" tone="warn" padding="lg">
          주의
        </Card>
      </>,
    );
    const c1 = screen.getByTestId('c1');
    expect(c1.tagName).toBe('DIV');
    expect(c1).toHaveAttribute('data-card-tone', 'default');
    expect(c1.className).toContain('rounded-2xl');
    const region = screen.getByRole('region', { name: '구역' });
    expect(region).toHaveAttribute('data-card-tone', 'warn');
  });

  it('StatusPill: 톤·점(accent)·글자 그대로', () => {
    renderWithProviders(
      <>
        <StatusPill tone="accent" dot data-testid="p1">
          {t('intake.status.가능')}
        </StatusPill>
        <StatusPill tone="strike" data-testid="p2">
          {t('intake.status.불가')}
        </StatusPill>
      </>,
    );
    expect(screen.getByTestId('p1')).toHaveAttribute('data-pill-tone', 'accent');
    expect(screen.getByTestId('p1').querySelector('[aria-hidden]')).not.toBeNull();
    expect(screen.getByTestId('p1')).toHaveTextContent(t('intake.status.가능'));
    expect(screen.getByTestId('p2').className).toContain('line-through');
  });

  it('SectionHeader: 질문형 h2(또는 h3) + 한 줄 안내 + id + 도구', () => {
    renderWithProviders(
      <>
        <SectionHeader
          id="s1"
          title="일정은 어디쯤 왔나요?"
          hint="공고문 날짜 그대로예요."
          actions={<button type="button">도구</button>}
        />
        <SectionHeader level={3} title="작은 제목" />
      </>,
    );
    const h2 = screen.getByRole('heading', { level: 2, name: '일정은 어디쯤 왔나요?' });
    expect(h2).toHaveAttribute('id', 's1');
    expect(screen.getByText('공고문 날짜 그대로예요.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '도구' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 3, name: '작은 제목' })).toBeInTheDocument();
  });

  it('FactList·FactRow: <dl> 안 이름(dt)·값(dd) — 값은 FactCell 이 라벨과 함께', () => {
    renderWithProviders(
      <FactList aria-label="돈">
        <FactRow label="계약금" hint="공고 비율">
          <FactCell
            fact={{ v: 31_240_000, label: '추정', prov: null, checked_at: null }}
            unit="won"
          />
        </FactRow>
      </FactList>,
    );
    const dl = screen.getByLabelText('돈');
    expect(dl.tagName).toBe('DL');
    expect(within(dl).getByText('계약금').tagName).toBe('DT');
    expect(within(dl).getByTestId('label-badge')).toHaveTextContent(t('label.estimated'));
    expect(within(dl).getByText('공고 비율')).toBeInTheDocument();
  });

  it('BigNumber: 이름 + 큰 값(FactCell) + 한 줄', () => {
    renderWithProviders(
      <BigNumber label="분양가" caption="84㎡ 기준" data-testid="big">
        <FactCell
          fact={{ v: 598_500_000, label: '확인됨', prov: null, checked_at: null }}
          unit="won"
        />
      </BigNumber>,
    );
    const big = screen.getByTestId('big');
    expect(big).toHaveTextContent('분양가');
    expect(big).toHaveTextContent('84㎡ 기준');
    expect(within(big).getByTestId('label-badge')).toHaveAttribute('data-tone', 'quiet');
  });

  it("KeepNote: 조건 이름 + '?' 용어 + 큰 값 + 근거 줄, warn 톤", () => {
    renderWithProviders(
      <MemoryRouter>
        <KeepNote
          label="되팔기 (전매)"
          term="resale_end"
          value="2026.12.09부터"
          detail="56일 남음"
          tone="warn"
          data-testid="kn"
        />
      </MemoryRouter>,
    );
    const note = screen.getByTestId('kn');
    expect(note).toHaveAttribute('data-note-tone', 'warn');
    expect(within(note).getByTestId('term')).toHaveAttribute('data-term', 'resale_end');
    expect(note).toHaveTextContent('2026.12.09부터');
    expect(note).toHaveTextContent('56일 남음');
  });

  it('Banner: 톤(warn·info·note)·굵은 첫 문장·아이콘(장식)·행동 버튼', () => {
    renderWithProviders(
      <Banner
        role="note"
        tone="info"
        title="처음 분석 중"
        icon
        actions={<button type="button">보기</button>}
        data-testid="b"
      >
        끝나면 채워져요
      </Banner>,
    );
    const b = screen.getByTestId('b');
    expect(b).toHaveAttribute('data-banner-tone', 'info');
    expect(within(b).getByText('처음 분석 중').tagName).toBe('B');
    expect(b.querySelector('svg')).toHaveAttribute('aria-hidden');
    expect(within(b).getByRole('button', { name: '보기' })).toBeInTheDocument();
  });

  it('Skeleton: 뼈대 줄(장식) + "불러오는 중…"(role=status, N9)', () => {
    renderWithProviders(<Skeleton lines={4} />);
    const s = screen.getByRole('status');
    expect(s).toHaveTextContent(t('app.loading'));
    expect(s.querySelectorAll('[aria-hidden]')).toHaveLength(4);
  });
});

describe('배지·라벨(목업 §3·§4)', () => {
  it('점수 배지 톤: 동률·재사용 = 회색 점선, 흔들림·근거와 달라요 = 주의 점선(글자 그대로)', () => {
    renderWithProviders(
      <>
        <TieBadge tie confidence={0.62} />
        <CachedBadge cached />
        <UnstableBadge unstable />
        <MismatchBadge mismatch />
      </>,
    );
    expect(screen.getByTestId('tie-badge')).toHaveAttribute('data-badge-tone', 'dashed');
    expect(screen.getByTestId('tie-badge')).toHaveTextContent(
      t('badge.tieWithConfidence', { confidence: '0.62' }),
    );
    expect(screen.getByTestId('cached-badge')).toHaveAttribute('data-badge-tone', 'dashed');
    expect(screen.getByTestId('unstable-badge')).toHaveAttribute('data-badge-tone', 'caution');
    expect(screen.getByTestId('mismatch-badge')).toHaveAttribute('data-badge-tone', 'caution');
    expect([t('badge.cached'), t('badge.unstable'), t('badge.mismatch')]).toEqual([
      '이전 결과 재사용',
      '순위가 흔들려요',
      '근거와 달라요',
    ]);
  });

  it('Badge: 의미는 글자(톤 7종 모두 글자를 그린다)', () => {
    const tones = [
      'neutral',
      'muted',
      'strong',
      'dashed',
      'caution',
      'cautionSolid',
      'accent',
    ] as const;
    renderWithProviders(
      <>
        {tones.map((tone) => (
          <Badge key={tone} tone={tone} data-testid={`b-${tone}`}>
            {tone}
          </Badge>
        ))}
      </>,
    );
    for (const tone of tones) expect(screen.getByTestId(`b-${tone}`)).toHaveTextContent(tone);
  });

  it("LabelBadge: '확인됨'은 조용한 글자, 나머지·사람 확인됨은 점선 배지(D28-2)", () => {
    renderWithProviders(
      <>
        <LabelBadge label="확인됨" />
        <LabelBadge label="추정" />
        <LabelBadge label="비공식" />
        <LabelBadge label="재가공" />
        <LabelBadge label="확인 불가" reason="403" />
        <LabelBadge label="확인됨" human />
      </>,
    );
    const badges = screen.getAllByTestId('label-badge');
    expect(badges.map((b) => b.getAttribute('data-tone'))).toEqual([
      'quiet',
      'badge',
      'badge',
      'badge',
      'badge',
      'badge',
    ]);
    expect(badges[5]).toHaveTextContent('사람 확인됨');
    expect(badges[1]?.className).toContain('border-dashed');
  });

  it('LabelBadge: 사유 40자 넘으면 줄이고 title 에 전문(#201)', () => {
    const reason = '가'.repeat(41);
    renderWithProviders(<LabelBadge label="추정" reason={reason} />);
    const badge = screen.getByTestId('label-badge');
    expect(badge.textContent).toContain('…(전체는 숫자를 눌러 보기)');
    expect(badge.getAttribute('title')).toContain(reason);
  });

  it("EmptyState: 문장 속 '확인 불가(사유)'는 점선 배지(SH-12), 블록은 role=status 상자", () => {
    renderWithProviders(
      <>
        <EmptyState inline reasonCode="not_collected" reason="raw" />
        <EmptyState message={t('empty.noData')} />
      </>,
    );
    const inline = screen.getAllByTestId('empty-state')[0] as HTMLElement;
    expect(inline).toHaveAttribute('data-tone', 'badge');
    expect(inline).toHaveTextContent(t('empty.reasonPlain.not_collected'));
    expect(inline).toHaveAttribute('title', t('empty.reasonOriginal', { reason: 'raw' }));
    expect(screen.getByRole('status')).toHaveTextContent(t('empty.noData'));
  });

  it('IntakeBadge 알약(목업 §4): 가능 = 주색+점, 미정 = 테두리, 확인 불가 = 회색, 불가 = 상태 글자 취소선', () => {
    const base = {
      path: 'official_popup' as const,
      reason: null,
      evidence_url: null,
      checked_at: '2026-10-08',
      http_status: 200,
    };
    renderWithProviders(
      <>
        <IntakeBadge intake={{ ...base, status: '가능' }} />
        <IntakeBadge intake={{ ...base, status: '미정' }} />
        <IntakeBadge intake={{ ...base, status: '확인 불가' }} />
        <IntakeBadge intake={{ ...base, status: '불가' }} />
      </>,
    );
    const pills = screen.getAllByTestId('intake-badge');
    expect(pills.map((p) => p.getAttribute('data-pill-tone'))).toEqual([
      'accent',
      'outline',
      'muted',
      'neutral',
    ]);
    expect(pills[0]?.querySelector('[aria-hidden]')).not.toBeNull();
    expect(pills[3]?.querySelector('.line-through')).toHaveTextContent(t('intake.status.불가'));
    expect(pills[3]).toHaveTextContent(
      `${t('intake.status.불가')} · ${t('intake.path.official_popup')}`,
    );
    expect(t('intake.path.headless_shot')).toBe('홈페이지 화면 캡처');
  });
});

describe('작업 진행(목업 §6, D30-8·SH-16)', () => {
  it('작업 이름·단계는 쉬운 말(모르는 값은 원문), 서버 원문은 title', () => {
    expect(jobNameText('region.bootstrap')).toBe(ko.job.name.region_bootstrap);
    expect(jobNameText('rejudge')).toBe('다시 판정');
    expect(jobNameText('new.kind')).toBe('new.kind');
    expect(jobStepText('decide')).toBe(ko.job.stepName.decide);
    expect(jobStepText('mystery')).toBe('mystery');
    renderWithProviders(
      <JobProgressView
        job={{
          id: 1,
          job_name: 'region.bootstrap',
          status: 'running',
          error_text: null,
          progress: { done: 62, total: 100, step: 'parse' },
        }}
      />,
    );
    const name = screen.getByTestId('job-name');
    expect(name).toHaveTextContent(ko.job.name.region_bootstrap);
    expect(name).toHaveAttribute('title', 'region.bootstrap');
    const status = screen.getByRole('status');
    expect(status).toHaveTextContent(t('job.status.running'));
    expect(status).toHaveTextContent(t('job.step', { step: ko.job.stepName.parse }));
    expect(status).toHaveTextContent('62/100');
    expect(screen.getByRole('progressbar')).toHaveAttribute('max', '100');
  });

  it('진행 수가 없으면 끝을 모르는 줄무늬 막대(role=progressbar, 값 없음)', () => {
    renderWithProviders(
      <JobProgressView job={{ id: 2, job_name: 'rejudge', status: 'queued', error_text: null }} />,
    );
    const bar = screen.getByTestId('job-indeterminate');
    expect(bar).toHaveAttribute('role', 'progressbar');
    expect(bar).not.toHaveAttribute('aria-valuenow');
    expect(bar.className).toContain('sa-indeterminate');
    expect(t('job.status.running')).toBe('진행 중');
  });
});

describe('차트 틀의 표(목업 §8, SH-18)', () => {
  it('표 이름(caption)을 보이고, 줄이 없으면 머리 + "데이터 없음" 한 줄', async () => {
    renderWithProviders(
      <DataTableToggle
        caption="차트 제목"
        table={{
          columns: [
            { key: 'name', header: '이름' },
            { key: 'v', header: '값' },
          ],
          rows: [],
        }}
      />,
    );
    const toggle = screen.getByRole('button', { name: t('table.show') });
    await userEvent.click(toggle);
    expect(screen.getByRole('button', { name: t('table.hide') })).toHaveAttribute(
      'aria-expanded',
      'true',
    );
    const table = screen.getByRole('table', { name: t('table.caption', { title: '차트 제목' }) });
    expect(within(table).getAllByRole('columnheader')).toHaveLength(2);
    expect(within(table).getByTestId('table-empty')).toHaveTextContent(t('empty.noData'));
    expect(within(table).getByTestId('table-empty')).toHaveAttribute('colspan', '2');
  });
});

describe("용어 '?'(목업 §3·§10)", () => {
  it("동그란 '?' 버튼 · 팝오버에 이름·뜻·'용어 사전에서 보기'(쿼리 유지)", async () => {
    renderWithProviders(
      <MemoryRouter initialEntries={['/complexes?region=1&scenario=B&x=1']}>
        <Term k="resale_limit">전매</Term>
      </MemoryRouter>,
    );
    const button = screen.getByTestId('term');
    expect(button).toHaveTextContent('?');
    await userEvent.click(button);
    const pop = document.getElementById(button.getAttribute('aria-controls') ?? '') as HTMLElement;
    expect(pop).toHaveAttribute('data-term-sheet', 'popover');
    expect(pop).toHaveTextContent(ko.glossary.items.resale_limit.term);
    expect(pop).toHaveTextContent(ko.glossary.items.resale_limit.short);
    expect(within(pop).getByRole('link', { name: t('glossary.more') })).toHaveAttribute(
      'href',
      '/glossary?region=1&scenario=B#resale_limit',
    );
  });

  it('휴대폰은 아래에서 올라오는 판 + 뒤 어둡게 + 닫기(SH-19)', async () => {
    const original = window.matchMedia;
    window.matchMedia = ((query: string) => ({
      ...original(query),
      matches: query === MOBILE_QUERY,
    })) as typeof window.matchMedia;
    try {
      renderWithProviders(
        <MemoryRouter>
          <Term k="resale_limit" />
        </MemoryRouter>,
      );
      const button = screen.getByTestId('term');
      await userEvent.click(button);
      const sheet = document.getElementById(
        button.getAttribute('aria-controls') ?? '',
      ) as HTMLElement;
      expect(sheet).toHaveAttribute('data-term-sheet', 'bottom');
      await userEvent.click(within(sheet).getByRole('button', { name: t('glossary.close') }));
      expect(button).toHaveAttribute('aria-expanded', 'false');
    } finally {
      window.matchMedia = original;
    }
  });

  it("라우터 밖(차트 갤러리 등)에서는 '용어 사전에서 보기' 링크가 없다(#264)", async () => {
    renderWithProviders(<Term k="resale_limit" />);
    await userEvent.click(screen.getByTestId('term'));
    expect(screen.queryByRole('link', { name: t('glossary.more') })).toBeNull();
  });
});

describe('라벨 뜻(SH-1·GL-1)', () => {
  it('여섯 줄 = 라벨 이름(배지 모양) + label.help 한 문장, Esc 로 접힘', async () => {
    renderWithProviders(<ProvenanceLegend />);
    expect(screen.getByText(t('label.legend'))).toBeInTheDocument();
    const toggle = screen.getByRole('button', { name: t('label.legendHelp') });
    await userEvent.click(toggle);
    const list = screen.getByRole('list', { name: t('label.legendHelp') });
    const rows = within(list).getAllByRole('listitem');
    expect(rows).toHaveLength(6);
    expect(rows.map((r) => within(r).getByTestId('label-badge').textContent)).toEqual([
      '확인됨',
      '추정',
      '비공식',
      '재가공',
      '확인 불가',
      '사람 확인됨',
    ]);
    expect(rows[0]).toHaveTextContent(ko.label.help.confirmed);
    await userEvent.keyboard('{Escape}');
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
  });
});

describe("출처 창 '이 값은 어디서 왔나요?'(목업 §3, SH-11)", () => {
  function serve(p: Provenance) {
    server.use(http.get(mswPath('/provenance/:id'), () => HttpResponse.json(p)));
  }

  it('제목·종류 칩·무엇·원문 파일 줄·출처 종류 안내, 다른 출처 없으면 "엇갈리는 출처 없음"', async () => {
    const p = { ...provenanceConflict(), conflicts: [], conflict_group: null } as Provenance;
    serve(p);
    renderWithProviders(
      <FactCell fact={{ v: 1, label: '확인됨', prov: p.id, checked_at: null }} unit="count" />,
    );
    await userEvent.click(screen.getByRole('button'));
    const panel = await screen.findByRole('dialog', { name: t('provenance.title') });
    expect(t('provenance.title')).toBe('이 값은 어디서 왔나요?');
    expect(within(panel).getByTestId('provenance-kind')).toHaveTextContent(
      t(`provenance.kind.${p.kind}` as 'provenance.kind.field'),
    );
    if (p.entity || p.field) {
      expect(within(panel).getByText(t('provenance.what'))).toBeInTheDocument();
    }
    expect(within(panel).getByText(t('provenance.checkedAt'))).toBeInTheDocument();
    expect(within(panel).getByText(t('provenance.noConflicts'))).toBeInTheDocument();
    if (p.raw_document_id !== null) {
      expect(within(panel).getByText(t('provenance.rawDocument'))).not.toHaveClass('sr-only');
    }
    expect(within(panel).getByText(t('provenance.kindsNote'))).toBeInTheDocument();
    expect(within(panel).getByRole('button', { name: t('provenance.close') })).toHaveFocus();
  });

  it("검증 모순으로 낮춘 값: '낮춤(검증 모순)' 배지 + 풀리는 조건 문장", async () => {
    const p = {
      ...provenanceConflict(),
      label: '확인 불가',
      reason: '검증 모순 — 공고문과 다름',
      conflicts: [],
      conflict_group: null,
    } as Provenance;
    serve(p);
    renderWithProviders(
      <FactCell fact={{ v: 1, label: '확인됨', prov: p.id, checked_at: null }} unit="count" />,
    );
    await userEvent.click(screen.getByRole('button'));
    const block = await screen.findByTestId('provenance-demoted');
    expect(block).toHaveTextContent(t('provenance.demoted'));
    expect(block).toHaveTextContent(t('provenance.demotedHint'));
    expect(t('provenance.demotedHint')).toContain('사람이 확인하거나');
  });
});

describe('불러오는 중 · 오류 · 빈 상태(목업 §7)', () => {
  const Wrap = ({ query }: { query: Parameters<typeof QueryState<string>>[0]['query'] }) => (
    <MemoryRouter>
      <QueryState query={query}>{(d) => <p>{d}</p>}</QueryState>
    </MemoryRouter>
  );

  it('불러오는 중 = 뼈대 + "불러오는 중…"', () => {
    renderWithProviders(<Wrap query={{ data: undefined, error: null, isLoading: true }} />);
    expect(screen.getByTestId('skeleton')).toHaveTextContent(t('app.loading'));
  });

  it('일반 오류 = "불러오지 못했어요: 내용" + 잠시 뒤 + 다시 시도(N10)', async () => {
    const refetch = vi.fn();
    renderWithProviders(
      <Wrap query={{ data: undefined, error: new Error('boom'), isLoading: false, refetch }} />,
    );
    const card = screen.getByTestId('query-error');
    expect(card).toHaveAttribute('role', 'alert');
    expect(card).toHaveTextContent(t('page.common.loadError', { detail: 'boom' }));
    expect(card).toHaveTextContent(t('page.common.loadErrorHint'));
    await userEvent.click(within(card).getByRole('button', { name: t('app.retry') }));
    expect(refetch).toHaveBeenCalled();
  });

  it('저장본 검증 실패(SH-17) = 주의 카드 role=alert', () => {
    const error = new ApiError('stored_view_mismatch', '해시 다름', 500);
    renderWithProviders(<Wrap query={{ data: undefined, error, isLoading: false }} />);
    const card = screen.getByTestId('query-error');
    expect(card).toHaveAttribute('data-card-tone', 'warn');
    expect(card).toHaveTextContent(t('page.common.storedViewMismatch', { detail: '해시 다름' }));
  });

  it('만드는 중(503) = 상태 카드 + 다시 시도', () => {
    const error = new ApiError('materialize_pending', 'wait', 503);
    renderWithProviders(
      <Wrap query={{ data: undefined, error, isLoading: false, refetch: () => undefined }} />,
    );
    const card = screen.getByTestId('materialize-pending');
    expect(card).toHaveTextContent(t('page.common.materializePendingStill'));
    expect(within(card).getByRole('button', { name: t('app.retry') })).toBeInTheDocument();
  });
});

describe('알림(목업 §6, toast)', () => {
  function Push({ items }: { items: ToastInput[] }) {
    const toast = useToast();
    useEffect(() => {
      for (const item of items) toast(item);
    }, [items, toast]);
    return null;
  }

  it('어두운 바탕 알림 · 행동 버튼은 실행 후 닫힘 · × 로 닫힘 · 최대 4개', async () => {
    const onClick = vi.fn();
    const items: ToastInput[] = [
      { message: 'a1', duration: 0 },
      { message: 'a2', duration: 0 },
      { message: 'a3', duration: 0 },
      { message: 'a4', duration: 0, action: { label: '보기', onClick } },
      { message: 'a5', duration: 0 },
    ];
    renderWithProviders(
      <ToastProvider>
        <Push items={items} />
      </ToastProvider>,
    );
    const region = screen.getByRole('region', { name: t('app.notifications') });
    expect(within(region).getAllByRole('status')).toHaveLength(4);
    expect(within(region).queryByText('a1')).toBeNull();
    expect(within(region).getAllByRole('status')[0]?.className).toContain('bg-toast');
    await userEvent.click(within(region).getByRole('button', { name: '보기' }));
    expect(onClick).toHaveBeenCalled();
    expect(within(region).queryByText('a4')).toBeNull();
    const close = within(region).getAllByRole('button', { name: t('app.toastClose') });
    await userEvent.click(close[0] as HTMLElement);
    expect(within(region).getAllByRole('status')).toHaveLength(2);
  });

  it('기본 8초 뒤 닫힘, duration 0 은 남는다', () => {
    vi.useFakeTimers();
    try {
      renderWithProviders(
        <ToastProvider>
          <Push items={[{ message: 'short' }, { message: 'stay', duration: 0 }]} />
        </ToastProvider>,
      );
      expect(screen.getByText('short')).toBeInTheDocument();
      act(() => {
        vi.advanceTimersByTime(8_100);
      });
      expect(screen.queryByText('short')).toBeNull();
      expect(screen.getByText('stay')).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });
});
