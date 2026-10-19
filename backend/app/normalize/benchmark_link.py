"""벤치마크 단지 매칭 — 이름이 바뀐 단지를 판정기로 잇기 (D31-6).

공고 이름과 실거래 이름이 전혀 다른 단지가 있다('제일풍경채 검단Ⅰ' 공고 ↔ 실거래 '신검단중앙역풍경채어바니티').
문자열 매칭(D10-5·D31-2)으로 못 이은 공고마다, 같은 법정동에서 준공 연도가 입주예정 연도 ±``YEAR_SLACK`` 인(또는 분양권
거래만 있어 건축년도가 없는) 아직 안 이어진 실거래 묶음을 후보로 모은다. 어느 후보가 같은 단지인지는 판정기
classify(``judge.pipeline.p4_classify_benchmark_link``, auto 만)가 정한다 — 이 모듈은 후보를 좁히고 입력 문구를 만들
뿐이다(AGENTS 규칙 3: 같은 단지인지 판단은 판정기만).

대상 공고 = ``_cases`` 가 남긴 사유가 '실거래 없음(매칭 단지 없음)'·'입주 전(분양권 거래 없음)'·'실거래 없음(입주 후 거래
없음)'인 것(마지막은 이름으로 이은 묶음에 입주 뒤 거래가 없는 경우 — 판정기가 고른 묶음을 합친다).
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from typing import Final

from sqlalchemy.orm import Session

from app.models import LegalDong, Region

__all__ = [
    "LINK_REASONS",
    "MAX_CANDIDATES",
    "YEAR_SLACK",
    "LinkCandidate",
    "LinkRequest",
    "link_requests",
]

LINK_REASONS: Final = (
    "실거래 없음(매칭 단지 없음)",
    "입주 전(분양권 거래 없음)",
    "실거래 없음(입주 후 거래 없음)",
)
YEAR_SLACK: Final = 1
MAX_CANDIDATES: Final = 30


@dataclass(frozen=True)
class LinkCandidate:
    cid: str  # classify 클래스 id ('g1' …)
    name: str  # 정규화 이름(실거래 묶음 키)
    dong: str
    text: str  # 클래스 설명


@dataclass(frozen=True)
class LinkRequest:
    key: str  # '<주택관리번호>:<공고번호>'
    text: str  # classify 항목(공고 단지 설명)
    candidates: tuple[LinkCandidate, ...]


def _notice_row(text: str, hm: str) -> dict[str, object]:
    from app.normalize.benchmark import json_object_at

    span = json_object_at(text, "HOUSE_MANAGE_NO", hm)
    if span is None:
        return {}
    try:
        row = json.loads(text[span[0] : span[1]])
    except json.JSONDecodeError:
        return {}
    return row if isinstance(row, dict) else {}


def link_requests(session: Session, region_id: int, asof_date: str) -> list[LinkRequest]:
    """문자열로 못 이은 공고마다 판정기에 물을 후보(같은 동, 준공 연도 ±1, 아직 안 이어진 묶음)."""
    from app.normalize import benchmark as bm

    region = session.get(Region, region_id)
    if region is None:
        raise LookupError(f"region {region_id} 없음")
    res = bm.BenchmarkBuild()
    bm._cases(session, region, asof_date, res)
    notices = {n.pb: n for n in bm._notices(session, region_id)}
    scope = set(region.legal_dong_codes or [])
    all_groups = bm._trade_groups(session, region_id)
    index = bm.LegalIndex(session, (n.address for n in notices.values()))
    # 후보에서 뺄 묶음 = 공고와 이어진 묶음 + 이름으로 어떤 공고와든 이어지는 묶음(84㎡ 없음 등으로 먼저 빠진 공고 포함 —
    # 자기 공고가 따로 있는 단지를 다른 공고 후보로 내지 않는다)
    used = set(res.matched_groups)
    for other in notices.values():
        code = index.code(other.address, scope)
        legal = session.get(LegalDong, code) if code else None
        if legal is None:
            continue
        d, sgg = bm._dong_name(legal), legal.sigungu_code
        hits = (
            bm._match(bm.normalize_apt_name(other.name), d, sgg, all_groups)
            or bm._match_tail(other.name, d, sgg, all_groups)[0]
        )
        used.update((g.name, g.dong) for g in hits)
    groups = [g for g in all_groups if (g.name, g.dong) not in used]
    out: list[LinkRequest] = []
    for u in res.unmatched:
        n = notices.get(u["notice_no"])
        if n is None or u["reason"] not in LINK_REASONS or not n.move_in_ym:
            continue
        code = index.code(n.address, scope)
        legal = session.get(LegalDong, code) if code else None
        if legal is None:
            continue
        dong, sgg = bm._dong_name(legal), legal.sigungu_code
        move_year = int(n.move_in_ym[:4])
        picked: list[tuple[int, bm._Group, int | None]] = []
        for g in groups:
            if not bm._same_place(g, dong, sgg):
                continue
            years = Counter(t.completed_year for t in g.trades if t.completed_year and not t.is_presale)
            year = years.most_common(1)[0][0] if years else None
            if year is not None and abs(year - move_year) > YEAR_SLACK:
                continue
            if year is None and not all(t.is_presale for t in g.trades):
                continue
            picked.append((abs(year - move_year) if year is not None else YEAR_SLACK, g, year))
        if not picked:
            continue
        picked.sort(key=lambda x: (x[0], x[1].name))
        row = _notice_row(n.text, n.hm)
        facts = [
            f"청약 공고 단지: {n.name}",
            f"공급 위치: {n.address or legal.full_name}",
            f"입주 예정: {n.move_in_ym}",
            f"모집공고일: {n.notice_date or '없음'}",
        ]
        for label, field in (
            ("공급 세대수", "TOT_SUPLY_HSHLDCO"),
            ("시공사", "CNSTRCT_ENTRPS_NM"),
            ("사업주체", "BSNS_MBY_NM"),
        ):
            if row.get(field):
                facts.append(f"{label}: {row[field]}")
        cands: list[LinkCandidate] = []
        for i, (_d, g, year) in enumerate(picked[:MAX_CANDIDATES], start=1):
            raw = Counter(t.apt_name for t in g.trades).most_common(1)[0][0]
            pre = sum(t.is_presale for t in g.trades)
            days = sorted(t.deal_date[:7] for t in g.trades)
            built = f"건축년도 {year}" if year is not None else "건축년도 없음(분양권 거래만)"
            cands.append(
                LinkCandidate(
                    f"g{i}", g.name, g.dong,
                    f"실거래 단지 '{raw}' ({legal.full_name}, {built}, 거래 {len(g.trades)}건 중 분양권 {pre}건, "
                    f"{days[0]}~{days[-1]})",
                )
            )  # fmt: skip
        out.append(LinkRequest(f"{n.hm}:{n.pb}", " / ".join(facts), tuple(cands)))
    return out
