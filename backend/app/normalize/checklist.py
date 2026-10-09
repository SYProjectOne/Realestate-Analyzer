"""체크리스트·캘린더 항목 (R3 M7) — 사실 테이블에서 결정론적으로 ``checklist_item`` 을 만든다(멱등).

| kind | 항목(title) | due_date | 원천 |
| --- | --- | --- | --- |
| 중도금 | 중도금 N회차 납부일 | 회차 날짜 | 현재 납부 조건(최신 effective_from) ``interim_schedule`` |
| 만료 | 전매제한 종료(당첨자 발표일 + N개월, 산술) | winner_date + resale_months | complex (resale_months > 0) |
| 만료 | 거주의무 만료(입주예정월 + N개월, 추정) | move_in_ym 1일 + residency_months | complex (residency_months > 0) |
| 계약 | 계약 체결 마감 | 계약일 마지막 날 | complex.contract_dates (계약 0004 kind '계약') |
| 공고 예상 | 모집공고 예정 | 모집공고일(기준일 뒤) / 없음(공고 전 단지) | complex.notice_date · applyhome_id 없음 |
| 법적 확인 | 토지거래허가구역 여부·대지지분 기준 확인(확인 권고) · 비과세 거주요건 적용 여부 확인(확인 권고) | 없음 | meta §2-9: 코드가 확정할 수 없는 추정 항목 — 단지마다 |
| 법적 확인 | <항목> 확인(추정 값 v) | 없음 | 법적 사실 필드의 채택 출처 라벨이 '추정' |

규칙
- 단지 = 지역의 단지 중 제외가 **확정된** 것(범위 경계, 또는 판정기 classify auto 의 제외 클래스 — ``analysis.scope``
  규칙 1·2)이 아닌 것. 분류 전(미분류)·분류 미해결(decision ≠ auto, 판정 범위 '미해결')도 포함한다.
- 기준일 이전 날짜 항목은 새로 만들지 않는다(지난 일정). 이미 있는 항목은 그대로 둔다.
- 항목은 제목이 아니라 **(단지, 항목 키)** 로 찾는다(R3b N-M5). 키 = 항목 종류·필드(중도금 회차, 전매제한 종료,
  거주의무 만료, 계약 체결 마감, 모집공고 예정, 법적 확인 필드) — 제목에 값(개월 수·추정 값)이 들어 있어도 값이
  바뀌면 새 행을 만들지 않고 같은 열린(open) 항목의 kind·제목·due_date 를 고친다. done·na 는 사람 처리 결과라
  고치지 않는다. 옛 버전이 남긴 같은 키의 열린 항목이 둘 이상이면 하나(제목이 같은 것, 없으면 가장 새 것)만 남기고
  나머지는 'na' 로 닫는다. note 는 처음 만들 때만 쓴다(사람이 PATCH 로 고치는 칸).
- 단지 제외가 확정되면 그 단지의 열린 항목을 'na' 로 닫는다(미해결이면 닫지 않는다).
판단 없음 — 날짜 산술과 표 조회뿐이다.
"""

# ruff: noqa: E501  (한국어 docstring·발췌 문구)

from __future__ import annotations

import calendar
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.scope import BOUNDARY_CLASS
from app.analysis.scope import EXCLUDED_CLASSES as JUDGE_EXCLUDED
from app.models import ChecklistItem, Complex, FieldProvenance, PaymentTerms

__all__ = [
    "EXCLUDED_CLASSES",
    "LEGAL_FIELDS",
    "ChecklistSync",
    "add_months_date",
    "excluded_for_checklist",
    "item_key",
    "sync_checklist",
]

EXCLUDED_CLASSES: Final = frozenset(
    {"public_sale", "public_rental", "private_rental", "non_apartment", "out_of_scope", "범위 경계"}
)
ALWAYS_LEGAL: Final = (
    "토지거래허가구역 여부·대지지분 기준 확인(확인 권고)",
    "비과세 거주요건 적용 여부 확인(확인 권고)",
)
LEGAL_FIELDS: Final[dict[str, str]] = {
    "resale_months": "전매제한 기간",
    "resale_release_on_registration": "등기 시 전매 해제 여부",
    "residency_months": "거주의무 기간",
    "rewin_restriction_years": "재당첨 제한 기간",
    "price_cap": "분양가상한제 적용 여부",
    "regulated": "규제지역 여부",
    "land_type": "택지 구분",
}


@dataclass(frozen=True)
class _Want:
    complex_id: int
    kind: str
    title: str
    due_date: str | None
    note: str | None
    key: str  # 항목 키(제목의 값이 바뀌어도 같은 항목) — ``item_key``


PROTECTED_KINDS: Final = frozenset({"사실 재확인"})
"""동기화가 고치거나 닫지 않는 kind — '사실 재확인'(D10-3 강등, 계약 .6)은 API(강등·복원)가 만들고 닫는다."""
_INTERIM_RE: Final = re.compile(r"^중도금 (\d+)회차 납부일$")
_PREFIX_KEYS: Final = (("전매제한 종료", "resale_end"), ("거주의무 만료", "residency_end"))
_EXACT_KEYS: Final = {"계약 체결 마감": "contract_end", "모집공고 예정": "notice"}


def item_key(kind: str, title: str) -> str:
    """항목 키: 자동 항목은 종류·필드(값 무관), 그 밖(사람이 만든 항목)은 kind+제목 그대로."""
    m = _INTERIM_RE.match(title)
    if m:
        return f"interim:{int(m.group(1))}"
    for prefix, key in _PREFIX_KEYS:
        if title.startswith(prefix):
            return key
    if title in _EXACT_KEYS:
        return _EXACT_KEYS[title]
    if title in ALWAYS_LEGAL:
        return f"legal:{title}"
    for fname, label in LEGAL_FIELDS.items():
        if title.startswith(f"{label} 확인(추정 값"):
            return f"legal:{fname}"
    return f"title:{kind}:{title}"


def excluded_for_checklist(cx: Complex) -> bool:
    """제외 확정(범위 경계, 또는 classify auto 의 제외 클래스)인가 — 미해결이면 False(``analysis.scope`` 규칙 1·2)."""
    if cx.inclusion_class == BOUNDARY_CLASS:
        return True
    return cx.inclusion_class in JUDGE_EXCLUDED and cx.inclusion_decision == "auto"


@dataclass
class ChecklistSync:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    closed: int = 0
    by_kind: dict[str, int] = field(default_factory=dict)

    def stats(self) -> dict[str, Any]:
        return {
            "inserted": self.inserted,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "closed": self.closed,
            "by_kind": dict(self.by_kind),
        }


def add_months_date(ymd: str, months: int) -> str | None:
    """'2026-09-20' + 12 → '2027-09-20' (말일 넘침은 그 달 말일)."""
    try:
        y, m, d = int(ymd[:4]), int(ymd[5:7]), int(ymd[8:10])
    except (ValueError, IndexError):
        return None
    total = y * 12 + (m - 1) + months
    ny, nm = total // 12, total % 12 + 1
    return f"{ny:04d}-{nm:02d}-{min(d, calendar.monthrange(ny, nm)[1]):02d}"


def _v(x: Any) -> Any:
    """Fact dict({v: …}) 로 저장된 값도 읽는다."""
    return x.get("v") if isinstance(x, dict) else x


def _day(x: Any) -> str | None:
    s = _v(x)
    if not isinstance(s, str) or len(s) < 10:
        return None
    s = s[:10]
    return s if s[4] == "-" and s[7] == "-" else None


def _current_terms(terms: list[PaymentTerms]) -> PaymentTerms | None:
    return max(terms, key=lambda t: (t.effective_from or "", t.id)) if terms else None


def _contract_end(items: list[Any]) -> str | None:
    days: list[str] = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        for k in ("to", "end", "date", "from", "start"):
            d = _day(it.get(k))
            if d:
                days.append(d)
    return max(days) if days else None


def _wants(
    cx: Complex, terms: list[PaymentTerms], estimated: dict[str, str | None], asof: str
) -> list[_Want]:
    out: list[_Want] = []

    def want(kind: str, title: str, due: str | None, note: str | None) -> None:
        out.append(_Want(cx.id, kind, title, due, note, item_key(kind, title)))

    def dated(kind: str, title: str, due: str | None, note: str | None) -> None:
        if due is not None and due >= asof:
            want(kind, title, due, note)

    cur = _current_terms(terms)
    if cur is not None:
        for it in cur.interim_schedule or []:
            if not isinstance(it, dict):
                continue
            seq = _v(it.get("seq"))
            pct = _v(it.get("pct"))
            if not isinstance(seq, int):
                continue
            note = f"자동: 공고 {cur.notice_no}({cur.notice_kind or '공급'}) 납부 조건" + (
                f", {pct}%" if pct is not None else ""
            )
            dated("중도금", f"중도금 {seq}회차 납부일", _day(it.get("due_date")), note)
    if cx.winner_date and cx.resale_months:
        end = add_months_date(cx.winner_date, int(cx.resale_months))
        note = "자동: 당첨자 발표일 기산" + (
            " · 등기 시 해제 가능" if cx.resale_release_on_registration else ""
        )
        dated("만료", f"전매제한 종료(당첨자 발표일 + {cx.resale_months}개월, 산술)", end, note)
    if cx.move_in_ym and cx.residency_months:
        end = add_months_date(f"{cx.move_in_ym}-01", int(cx.residency_months))
        dated(
            "만료",
            f"거주의무 만료(입주예정월 + {cx.residency_months}개월, 추정)",
            end,
            "자동: 실제 기산일은 최초 입주가능일 — 입주예정월 1일로 추정",
        )
    end_contract = _contract_end(cx.contract_dates)
    dated("계약", "계약 체결 마감", end_contract, "자동: 청약홈 계약일")
    if cx.applyhome_id is None:
        want("공고 예상", "모집공고 예정", None, "자동: 공고 전 단지 — 청약홈 공고 확인")
    else:
        nd = _day(cx.notice_date)
        if nd is not None and nd > asof:
            want("공고 예상", "모집공고 예정", nd, "자동: 청약홈 모집공고일")
    for title in ALWAYS_LEGAL:
        want("법적 확인", title, None, "자동: 코드가 확정하지 않는 항목(meta 확인 권고)")
    for fname, label in LEGAL_FIELDS.items():
        if fname in estimated:
            shown = estimated[fname]
            want(
                "법적 확인",
                f"{label} 확인(추정 값 {shown})" if shown is not None else f"{label} 확인(추정 값)",
                None,
                "자동: 채택 출처 라벨 '추정'",
            )
    return out


def _estimated(session: Session, complex_ids: list[int]) -> dict[int, dict[str, str | None]]:
    out: dict[int, dict[str, str | None]] = defaultdict(dict)
    if not complex_ids:
        return out
    for fp in session.scalars(
        select(FieldProvenance).where(
            FieldProvenance.entity == "complex",
            FieldProvenance.entity_id.in_(complex_ids),
            FieldProvenance.field.in_(tuple(LEGAL_FIELDS)),
            FieldProvenance.chosen.is_(True),
            FieldProvenance.label == "추정",
        )
    ):
        if fp.entity_id is not None:
            out[fp.entity_id][fp.field] = fp.value_text
    return out


def sync_checklist(session: Session, region_id: int, *, asof_date: str) -> ChecklistSync:
    """지역 단지들의 체크리스트 항목을 사실 테이블과 맞춘다. flush 만 한다(commit 은 호출자)."""
    res = ChecklistSync()
    complexes = list(
        session.scalars(select(Complex).where(Complex.region_id == region_id).order_by(Complex.id))
    )
    ids = [c.id for c in complexes]
    terms: dict[int, list[PaymentTerms]] = defaultdict(list)
    if ids:
        for t in session.scalars(select(PaymentTerms).where(PaymentTerms.complex_id.in_(ids))):
            terms[t.complex_id].append(t)
    estimated = _estimated(session, ids)
    existing: dict[tuple[int | None, str], list[ChecklistItem]] = defaultdict(list)
    if ids:
        for it in session.scalars(
            select(ChecklistItem).where(ChecklistItem.complex_id.in_(ids)).order_by(ChecklistItem.id)
        ):
            existing[(it.complex_id, item_key(it.kind, it.title))].append(it)
    for cx in complexes:
        if excluded_for_checklist(cx):
            for (cid, _k), group in existing.items():
                for it in group:
                    if cid == cx.id and it.status == "open" and it.kind not in PROTECTED_KINDS:
                        it.status = "na"
                        res.closed += 1
            continue
        for w in _wants(cx, terms.get(cx.id, []), estimated.get(cx.id, {}), asof_date):
            res.by_kind[w.kind] = res.by_kind.get(w.kind, 0) + 1
            group = existing[(w.complex_id, w.key)]
            if not group:
                it = ChecklistItem(
                    complex_id=w.complex_id,
                    kind=w.kind,
                    title=w.title,
                    due_date=w.due_date,
                    status="open",
                    note=w.note,
                )
                session.add(it)
                group.append(it)
                res.inserted += 1
                continue
            opens = [i for i in group if i.status == "open"]
            if not opens:
                res.unchanged += 1  # done·na — 사람 처리 결과는 고치지 않는다
                continue
            keep = next((i for i in opens if i.title == w.title), opens[-1])
            for extra in opens:
                if extra is not keep:  # 옛 버전이 남긴 같은 키의 열린 항목
                    extra.status = "na"
                    res.closed += 1
            if (keep.kind, keep.title, keep.due_date) != (w.kind, w.title, w.due_date):
                keep.kind, keep.title, keep.due_date = w.kind, w.title, w.due_date
                res.updated += 1
            else:
                res.unchanged += 1
    session.flush()
    return res
