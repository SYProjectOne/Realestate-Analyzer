/**
 * 공통 컴포넌트 완성 테스트 — 계약(fact.json·intake.json·provenance.json) 표시 규칙과
 * "숫자 셀 클릭 → 출처 패널(원문 발췌 하이라이트 + 상충 그룹)".
 */
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { provenanceConflict, provenanceScore } from '@/charts/gallery/fixtures';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { renderWithProviders } from '@/test/render';
import { t } from '@/i18n';
import {
  EmptyState,
  FactCell,
  IntakeBadge,
  JobProgressView,
  LabelBadge,
  ProvenanceLegend,
  RegionPicker,
  SnapshotPicker,
} from './index';

const RAW_TEXT = `${'가'.repeat(1180)}공급세대수 1,573세대${'나'.repeat(40)}`;

describe('라벨·배지 표시 문자열(계약 fact.json 규칙)', () => {
  it('확인 불가 → "확인 불가(사유, 확인일)"', () => {
    renderWithProviders(<LabelBadge label="확인 불가" reason="403" checkedAt="2026-10-07" />);
    expect(screen.getByText('확인 불가(403, 2026-10-07)')).toBeInTheDocument();
  });

  it('다른 라벨의 한정어 → "<라벨>(<사유>)"', () => {
    renderWithProviders(<LabelBadge label="추정" reason="대체·보정 c=0.015" />);
    expect(screen.getByText('추정(대체·보정 c=0.015)')).toBeInTheDocument();
  });

  it('human=true → "사람 확인됨"', () => {
    renderWithProviders(<LabelBadge label="확인됨" human />);
    expect(screen.getByText('사람 확인됨')).toBeInTheDocument();
  });

  it('FactCell: unit 생략 시 fact.unit 힌트(units → 세대)', () => {
    renderWithProviders(
      <FactCell
        fact={{ v: 185, label: '확인됨', prov: 'fp_262', checked_at: '2026-10-07', unit: 'units' }}
      />,
    );
    expect(screen.getByText('185세대')).toBeInTheDocument();
  });

  it('IntakeBadge: 확인 불가 → 사유·확인일, human_check → "사람" 접두', () => {
    renderWithProviders(
      <>
        <IntakeBadge
          intake={{
            status: '확인 불가',
            path: 'official_popup',
            checked_at: '2026-10-07T09:14:00+09:00',
            reason: '403',
          }}
        />
        <IntakeBadge intake={{ status: '가능', path: 'human_check', checked_at: '2026-10-09' }} />
      </>,
    );
    expect(screen.getByText('접수 확인 불가(403, 2026-10-07) · 공식 팝업')).toBeInTheDocument();
    expect(screen.getByText('접수 가능 · 사람 확인')).toBeInTheDocument();
  });
});

describe('R9-UI P3(D28-2): 라벨 무게 나누기 — 글자는 남고 무게만 바뀐다', () => {
  const LABEL_CASES = [
    ['확인됨', false],
    ['확인됨', true],
    ['추정', false],
    ['비공식', false],
    ['재가공', false],
    ['확인 불가', false],
  ] as const;

  it.each(LABEL_CASES)('라벨 %s(사람 확인 %s)는 비어 있지 않은 텍스트를 그린다', (label, human) => {
    renderWithProviders(<LabelBadge label={label} human={human} reason={null} />);
    const badge = screen.getByTestId('label-badge');
    expect(badge.textContent?.trim().length ?? 0).toBeGreaterThan(0);
  });

  it("'확인됨'만 조용한 글자(data-tone=quiet, 테두리 없음), 나머지는 테두리 배지", () => {
    renderWithProviders(
      <>
        <LabelBadge label="확인됨" />
        <LabelBadge label="확인됨" human />
        <LabelBadge label="추정" reason="산술" />
        <LabelBadge label="비공식" />
        <LabelBadge label="재가공" />
        <LabelBadge label="확인 불가" reason="403" />
      </>,
    );
    const badges = screen.getAllByTestId('label-badge');
    const quiet = badges.filter((b) => b.dataset.tone === 'quiet');
    expect(quiet).toHaveLength(1);
    expect(quiet[0]).toHaveTextContent(t('label.confirmed'));
    expect(quiet[0]?.className).not.toMatch(/\bborder\b/);
    for (const b of badges.filter((x) => x.dataset.tone !== 'quiet')) {
      expect(b.dataset.tone).toBe('badge');
      expect(b.className).toMatch(/\bborder\b/);
    }
    // 사람 확인됨은 테두리 배지 그대로(D28-2)
    expect(screen.getByText('사람 확인됨').dataset.tone).toBe('badge');
  });

  it('사유가 40자를 넘으면 화면은 줄여 보이고 title 에 전문을 둔다(라벨 글자는 그대로)', () => {
    const reason = `연수 505·검단 737·계양 0·김포 787·${'가'.repeat(30)} 합`;
    renderWithProviders(<LabelBadge label="재가공" reason={reason} />);
    const badge = screen.getByTestId('label-badge');
    const full = `재가공(${reason})`;
    expect(badge).toHaveAttribute('title', full);
    expect(badge.textContent).toBe(t('label.truncated', { text: full.slice(0, 40) }));
    expect(badge.textContent?.startsWith('재가공(')).toBe(true);
  });

  it('full 이면(출처 패널) 줄이지 않는다', () => {
    const reason = '가'.repeat(60);
    renderWithProviders(<LabelBadge label="추정" reason={reason} full />);
    expect(screen.getByTestId('label-badge')).toHaveTextContent(`추정(${reason})`);
  });

  it('출처 범례: 한 줄 안내 + 라벨 뜻(펼침) 6가지', async () => {
    renderWithProviders(<ProvenanceLegend />);
    expect(screen.getByText(t('label.legend'))).toBeInTheDocument();
    const toggle = screen.getByRole('button', { name: t('label.legendHelp') });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    const list = screen.getByRole('list', { name: t('label.legendHelp') });
    expect(within(list).getAllByRole('listitem')).toHaveLength(6);
    for (const key of [
      'confirmed',
      'estimated',
      'unofficial',
      'reprocessed',
      'unknown',
      'human',
    ] as const) {
      expect(within(list).getByText(t(`label.help.${key}`))).toBeInTheDocument();
    }
    await userEvent.keyboard('{Escape}');
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
  });
});

describe('R9-UI P7 원 사유는 title 에(EmptyState·LabelBadge·IntakeBadge)', () => {
  it('쉬운 말을 보이고 원 사유는 같은 요소 title', () => {
    renderWithProviders(
      <>
        <LabelBadge label="확인 불가" reason="발코니 표 해석 실패" checkedAt="2026-10-13" />
        <EmptyState inline reason="미판정" checkedAt="2026-10-14" />
        <IntakeBadge
          intake={{
            status: '확인 불가',
            path: 'headless_shot',
            checked_at: '2026-10-14',
            reason: '판정 미해결',
          }}
          showPath={false}
        />
      </>,
    );
    const label = screen.getByTestId('label-badge');
    expect(label).toHaveTextContent(
      `확인 불가(${t('empty.reasonPlain.parse_failed')}, 2026-10-13)`,
    );
    expect(label.getAttribute('title')).toContain(
      t('empty.reasonOriginal', { reason: '발코니 표 해석 실패' }),
    );
    const empty = screen.getByTestId('empty-state');
    expect(empty).toHaveTextContent(`확인 불가(${t('empty.reasonPlain.unjudged')}, 2026-10-14)`);
    expect(empty).toHaveAttribute('title', t('empty.reasonOriginal', { reason: '미판정' }));
    const intake = screen.getByTestId('intake-badge');
    expect(intake).toHaveTextContent(t('empty.reasonPlain.unresolved'));
    expect(intake.getAttribute('title')).toContain(
      t('empty.reasonOriginal', { reason: '판정 미해결' }),
    );
  });

  it('출처 패널(full)은 원 사유 그대로', () => {
    renderWithProviders(<LabelBadge label="확인 불가" reason="미판정" full />);
    expect(screen.getByTestId('label-badge')).toHaveTextContent('확인 불가(미판정)');
  });
});

describe('FactCell 클릭 → ProvenancePanel', () => {
  it('상충 그룹(채택·미채택)과 원문 발췌 하이라이트를 보여 준다', async () => {
    server.use(
      http.get(mswPath('/provenance/:prov_id'), () => HttpResponse.json(provenanceConflict())),
    );
    renderWithProviders(
      <FactCell
        fact={{ v: 1573, label: '확인됨', prov: 'fp_13001', checked_at: '2026-10-07' }}
        unit="households"
      />,
    );
    await userEvent.click(screen.getByRole('button', { name: /1,573세대/ }));
    const panel = await screen.findByRole('dialog', { name: '출처' });
    // 원문 주소(본 출처 + 상충 후보 각각)
    expect(
      (await within(panel).findAllByText('https://www.applyhome.co.kr/', { selector: 'a' })).length,
    ).toBeGreaterThan(0);

    // 발췌 안의 값은 <mark>로 강조
    const marks = within(panel).getAllByText('1,573', { selector: 'mark' });
    expect(marks.length).toBeGreaterThan(0);

    // 상충 그룹: 두 후보 모두, 채택 표시
    const group = within(panel).getByRole('list', { name: '상충 출처' });
    // 미채택 후보의 값 + 그 후보 발췌 안의 하이라이트
    expect(within(group).getAllByText('1,769').length).toBeGreaterThan(0);
    expect(within(group).getByText('1,769', { selector: 'mark' })).toBeInTheDocument();
    expect(within(group).getByText('미채택')).toBeInTheDocument();
    expect(within(group).getByText('채택')).toBeInTheDocument();
  });

  it('원문 텍스트를 열면 excerpt 오프셋 구간을 하이라이트한다', async () => {
    server.use(
      http.get(mswPath('/provenance/:prov_id'), () => HttpResponse.json(provenanceConflict())),
      http.get(mswPath('/raw/:raw_document_id'), () => HttpResponse.text(RAW_TEXT)),
    );
    renderWithProviders(
      <FactCell
        fact={{ v: 1573, label: '확인됨', prov: 'fp_13001', checked_at: '2026-10-07' }}
        unit="households"
      />,
    );
    await userEvent.click(screen.getByRole('button'));
    const panel = await screen.findByRole('dialog', { name: '출처' });
    await userEvent.click(await within(panel).findByRole('button', { name: '원문에서 보기' }));
    await waitFor(() =>
      expect(within(panel).getByText('공급세대수 1,573세대', { selector: 'mark' })).toBeVisible(),
    );
  });

  it('점수 성분 출처는 산출식을 보여 주고, Esc로 닫힌다', async () => {
    server.use(
      http.get(mswPath('/provenance/:prov_id'), () => HttpResponse.json(provenanceScore())),
    );
    renderWithProviders(
      <FactCell
        fact={{
          v: 5,
          label: '추정',
          reason: '대체·보정 c=0.015',
          prov: 'sc_88_4_gap',
          checked_at: '2026-10-08',
        }}
        unit="score"
      />,
    );
    await userEvent.click(screen.getByRole('button'));
    const panel = await screen.findByRole('dialog', { name: '출처' });
    expect(await within(panel).findByText(/혼재 중앙 0 → 5.0/)).toBeInTheDocument();
    await userEvent.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });
});

describe('계약 응답 모양을 그대로 받는 선택기·진행', () => {
  it('RegionPicker·SnapshotPicker: 숫자 id(계약)도 받는다', async () => {
    const onRegion = vi.fn();
    const onSnapshot = vi.fn();
    renderWithProviders(
      <>
        <RegionPicker
          regions={[
            { id: 1, name: '픽스처 지역' },
            { id: 2, name: '두 번째' },
          ]}
          value="1"
          onChange={onRegion}
          onAddRegion={() => {}}
        />
        <SnapshotPicker
          snapshots={[
            { id: 12, asof_date: '2026-10-08', status: 'published', degraded: false },
            { id: 11, asof_date: '2026-10-07', status: 'published', degraded: true },
          ]}
          value="12"
          onChange={onSnapshot}
        />
      </>,
    );
    await userEvent.selectOptions(screen.getByLabelText('지역'), '두 번째');
    expect(onRegion).toHaveBeenCalledWith('2');
    await userEvent.selectOptions(screen.getByLabelText('기준일'), '11');
    expect(onSnapshot).toHaveBeenCalledWith('11');
    expect(screen.getByRole('option', { name: /2026-10-07 · 일부 수집 실패/ })).toBeInTheDocument();
  });

  it('JobProgressView: 계약 progress(done/total·step)를 보여 준다', () => {
    renderWithProviders(
      <JobProgressView
        job={{
          id: 905,
          job_name: 'rejudge',
          status: 'running',
          error_text: null,
          progress: { done: 18, total: 19, step: 'decide' },
        }}
      />,
    );
    const status = screen.getByRole('status');
    expect(status).toHaveTextContent('18/19');
    expect(status).toHaveTextContent('decide');
    expect(screen.getByRole('progressbar')).toHaveAttribute('max', '19');
  });
});
