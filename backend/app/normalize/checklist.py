"""체크리스트·캘린더 항목 (R3 M7) — 사실 테이블에서 결정론적으로 ``checklist_item`` 을 만든다(멱등).

| kind | 항목(title) | due_date | 원천 |
| --- | --- | --- | --- |
| 중도금 | 중도금 N회차 납부일 | 회차 날짜 | 현재 납부 조건(최신 effective_from) ``interim_schedule`` |
| 만료 | 전매제한 종료(당첨자 발표일 + N개월, 산술) | winner_date + resale_months | complex (resale_months > 0) |
| 만료 | 거주의무 만료(입주예정월 + N개월, 추정) | move_in_ym 1일 + residency_months | complex (residency_months > 0) |
| 만료 | 계약 체결 마감 | 계약일 마지막 날 | complex.contract_dates — 계약 전용 kind 가 없어 '만료'(계약 변경 제안) |
| 공고 예상 | 모집공고 예정 | 모집공고일(기준일 뒤) / 없음(공고 전 단지) | complex.notice_date · applyhome_id 없음 |
| 법적 확인 | 토지거래허가구역 여부·대지지분 기준 확인(확인 권고) · 비과세 거주요건 적용 여부 확인(확인 권고) | 없음 | meta §2-9: 코드가 확정할 수 없는 추정 항목 — 단지마다 |
| 법적 확인 | <항목> 확인(추정 값 v) | 없음 | 법적 사실 필드의 채택 출처 라벨이 '추정' |

규칙
- 단지 = 지역의 단지 중 제외 클래스(공공·임대·비아파트·범위 밖·범위 경계)가 아닌 것. 분류 전(미분류)도 포함한다.
- 기준일 이전 날짜 항목은 새로 만들지 않는다(지난 일정). 이미 있는 항목은 그대로 둔다.
- 같은 (단지, kind, title) 은 한 행. 날짜가 바뀌면 열린(open) 항목만 due_date 를 고친다(done·na 는 사람 처리 결과).
  note 는 처음 만들 때만 쓴다(사람이 PATCH 로 고치는 칸).
- 단지가 제외 클래스로 바뀌면 그 단지의 열린 항목을 'na' 로 닫는다.
판단 없음 — 날짜 산술과 표 조회뿐이다.
"""

# ruff: noqa: E501  (한국어 docstring·발췌 문구)

from __future__ import annotations

import calendar
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ChecklistItem, Complex, FieldProvenance, PaymentTerms

__all__ = ["EXCLUDED_CLASSES", "LEGAL_FIELDS", "ChecklistSync", "add_months_date", "sync_checklist"]

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

    def dated(kind: str, title: str, due: str | None, note: str | None) -> None:
        if due is not None and due >= asof:
            out.append(_Want(cx.id, kind, title, due, note))

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
    dated("만료", "계약 체결 마감", end_contract, "자동: 청약홈 계약일")
    if cx.applyhome_id is None:
        out.append(_Want(cx.id, "공고 예상", "모집공고 예정", None, "자동: 공고 전 단지 — 청약홈 공고 확인"))
    else:
        nd = _day(cx.notice_date)
        if nd is not None and nd > asof:
            out.append(_Want(cx.id, "공고 예상", "모집공고 예정", nd, "자동: 청약홈 모집공고일"))
    for title in ALWAYS_LEGAL:
        out.append(_Want(cx.id, "법적 확인", title, None, "자동: 코드가 확정하지 않는 항목(meta 확인 권고)"))
    for fname, label in LEGAL_FIELDS.items():
        if fname in estimated:
            shown = estimated[fname]
            out.append(
                _Want(
                    cx.id,
                    "법적 확인",
                    f"{label} 확인(추정 값 {shown})" if shown is not None else f"{label} 확인(추정 값)",
                    None,
                    "자동: 채택 출처 라벨 '추정'",
                )
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
    existing: dict[tuple[int | None, str, str], ChecklistItem] = {}
    if ids:
        for it in session.scalars(
            select(ChecklistItem).where(ChecklistItem.complex_id.in_(ids)).order_by(ChecklistItem.id)
        ):
            existing.setdefault((it.complex_id, it.kind, it.title), it)
    for cx in complexes:
        if cx.inclusion_class in EXCLUDED_CLASSES:
            for (cid, _k, _t), it in existing.items():
                if cid == cx.id and it.status == "open":
                    it.status = "na"
                    res.closed += 1
            continue
        for w in _wants(cx, terms.get(cx.id, []), estimated.get(cx.id, {}), asof_date):
            res.by_kind[w.kind] = res.by_kind.get(w.kind, 0) + 1
            found = existing.get((w.complex_id, w.kind, w.title))
            if found is None:
                it = ChecklistItem(
                    complex_id=w.complex_id,
                    kind=w.kind,
                    title=w.title,
                    due_date=w.due_date,
                    status="open",
                    note=w.note,
                )
                session.add(it)
                existing[(w.complex_id, w.kind, w.title)] = it
                res.inserted += 1
            elif found.status == "open" and found.due_date != w.due_date:
                found.due_date = w.due_date
                res.updated += 1
            else:
                res.unchanged += 1
    session.flush()
    return res
