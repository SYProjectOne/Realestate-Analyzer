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
import {
  FactCell,
  IntakeBadge,
  JobProgressView,
  LabelBadge,
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
