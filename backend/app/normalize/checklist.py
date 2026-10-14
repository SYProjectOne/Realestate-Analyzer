"""체크리스트·캘린더 항목 (R3 M7) — 사실 테이블에서 결정론적으로 ``checklist_item`` 을 만든다(멱등).

| kind | 항목(title) | due_date | 원천 |
| --- | --- | --- | --- |
| 중도금 | 중도금 N회차 납부일 | 회차 날짜 | 현재 납부 조건(최신 effective_from) ``interim_schedule`` |
| 만료 | 전매제한 종료(당첨자 발표일 + N개월, 산술) | winner_date + resale_months | complex (resale_months > 0) |
| 만료 | 거주의무 만료(입주예정월 + N개월, 추정) | move_in_ym 1일 + residency_months | complex (residency_months > 0) |
| 계약 | 계약 체결 마감 | 계약일 마지막 날 | complex.contract_dates (계약 0004 kind '계약') |
| 공고 예상 | 모집공고 예정 | 모집공고일(기준일 뒤) / 없음(공고 전 단지) | complex.notice_date · applyhome_id 없음 |
| 청약 접수 | <순위·구분> 청약 접수[(<거주지역>·…)] · 청약 접수(잔여·임의 한 칸) | 접수 시작일 | complex.apply_dates(D29-3, 계약 .21) — 접수가 끝나지 않은 것(끝날짜 ≥ 기준일) |
| 당첨자 발표 | 당첨자 발표 | 당첨자 발표일 | complex.winner_date(D29-3) |
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
- D29-3 청약 접수: ``apply_dates`` 항목(R9-PARSE ``{kind, start, end}`` · 옛 ``{kind, date}``)을 순위·구분(kind 의 첫 낱말 —
  '1순위'·'특별공급'·'청약접수')과 같은 기간끼리 한 항목으로 묶는다 — 거주지역 구분은 제목 괄호('1순위 청약 접수(해당지역·
  기타지역)'). 기한 = 접수 시작일(달력에 접수 날), 접수 중(시작 < 기준일 ≤ 끝)인 것도 만든다. 메모 = 접수 기간. 키 = 'apply:' +
  제목의 구분 부분. 당첨자 발표 키 = 'winner'.
- D29-2: 병합된 단지 행(``complex.merged_into_id`` — 같은 사업의 중복 행)도 제외처럼 다룬다.
- R9-PARSE: 다른 단지의 납부 조건 공고번호를 주택관리번호로 가진 행(잔여 공고 번호로 따로 생긴 같은 사업의 두 번째 행 —
  ``absorbed_remnant_rows``)도 제외처럼 다룬다(같은 일정이 캘린더에 두 번 나오지 않게).
- M-9(계약 .8 ``closed_by``): 자동 항목의 근거 사실이 사라지거나 강등(검증 모순 — ``app.facts_view`` 오버레이로 읽는다)되면
  열린 항목을 'na'(closed_by 'auto')로 닫는다(모순 날짜를 계속 보이지 않게). 근거가 돌아오거나 제외됐던 단지가 다시
  포함되면 동기화가 닫은 항목(closed_by 'auto')만 다시 연다. 사람이 처리한 항목(closed_by 'human', 또는 0008 이전 done·na)은
  건드리지 않는다.
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
    "APPLY_KIND",
    "EXCLUDED_CLASSES",
    "LEGAL_FIELDS",
    "WINNER_KIND",
    "ChecklistSync",
    "absorbed_remnant_rows",
    "add_months_date",
    "apply_groups",
    "excluded_for_checklist",
    "item_key",
    "sync_checklist",
    "sync_checklist_for",
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
APPLY_KIND: Final = "청약 접수"
WINNER_KIND: Final = "당첨자 발표"
_APPLY_SUFFIX: Final = "청약 접수"
_APPLY_WHOLE: Final = "청약접수"
"""청약홈 잔여·임의 공고의 전체 접수 기간 한 칸(``applyhome_api_parser.APPLY_KINDS`` 끝) — 제목은 그냥 '청약 접수'."""
_APPLY_TITLE_RE: Final = re.compile(r"^(?:(?P<rank>\S+) )?청약 접수(?:\((?P<areas>[^()]+)\))?$")


def item_key(kind: str, title: str) -> str:
    """항목 키: 자동 항목은 종류·필드(값 무관), 그 밖(사람이 만든 항목)은 kind+제목 그대로."""
    m = _INTERIM_RE.match(title)
    if m:
        return f"interim:{int(m.group(1))}"
    if kind == APPLY_KIND:
        a = _APPLY_TITLE_RE.match(title)
        if a:
            areas = a.group("areas")
            return f"apply:{a.group('rank') or ''}" + (f"({areas})" if areas else "")
    if kind == WINNER_KIND and title == WINNER_KIND:
        return "winner"
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


def absorbed_remnant_rows(session: Session, region_id: int) -> set[int]:
    """같은 지역 **다른** 단지의 납부 조건 공고번호(``payment_terms.notice_no``)를 주택관리번호로 가진 단지 행 id — 잔여·임의
    공고 인용(D18-4)을 못 읽던 때 잔여 공고 번호로 따로 생긴 같은 사업의 두 번째 행이다(R9-PARSE: G7 캘린더에 '두산위브 더센트럴
    도화 · 중도금 3회차 납부일'이 두 번 — 원 단지 행 39(2025000397)와 임의공급 번호 행 99(2025940268)가 같은 중도금 일정을 냈다).
    원 단지가 그 공고의 일정을 이미 가지므로 이 행의 자동 항목은 만들지 않고 열린 것은 닫는다. 표 조회뿐이다(판단 아님)."""
    rows = session.execute(
        select(Complex.id, Complex.applyhome_id).where(
            Complex.region_id == region_id, Complex.applyhome_id.is_not(None)
        )
    ).all()
    by_no = {str(no): cid for cid, no in rows}
    # D29-2: 원 단지에 병합된 행(``complex.merged_into_id``)도 같은 사업의 두 번째 행이다
    out: set[int] = set(
        session.scalars(
            select(Complex.id).where(Complex.region_id == region_id, Complex.merged_into_id.is_not(None))
        )
    )
    for owner, no in session.execute(
        select(PaymentTerms.complex_id, PaymentTerms.notice_no)
        .join(Complex, Complex.id == PaymentTerms.complex_id)
        .where(Complex.region_id == region_id)
    ):
        cid = by_no.get(str(no))
        if cid is not None and cid != owner:
            out.add(cid)
    return out


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
    reopened: int = 0
    by_kind: dict[str, int] = field(default_factory=dict)

    def stats(self) -> dict[str, Any]:
        return {
            "inserted": self.inserted,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "closed": self.closed,
            "reopened": self.reopened,
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
    """현재 납부 조건 = ``analysis.price_view.current_terms``(effective_from → notice_no → id — 점수·화면과 같은 행,
    R3 4차 minor: 예전에는 notice_no 를 건너뛰어 같은 날 공고 둘이면 다른 행을 골랐다)."""
    from app.analysis.price_view import current_terms

    return current_terms(terms)


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


def apply_groups(apply_dates: Any) -> list[tuple[str, str, str]]:
    """``complex.apply_dates`` → [(제목, 시작일, 끝날짜)] (D29-3). 순위·구분(kind 첫 낱말)과 기간이 같은 항목을 묶고 거주지역 구분은
    제목 괄호에. 옛 모양 ``{kind, date}`` 는 시작 = 끝 = date. 날짜를 못 읽는 항목은 뺀다. 같은 제목이 다시 나오면 앞의 것(표 순서
    — ``APPLY_KINDS``)만. 문자열·날짜 정리뿐이다(판단 아님)."""
    groups: dict[tuple[str, str, str], list[str]] = {}
    for it in apply_dates or []:
        if not isinstance(it, dict):
            continue
        kind = str(_v(it.get("kind")) or "").strip()
        start = _day(it.get("start")) or _day(it.get("date"))
        end = _day(it.get("end")) or start
        if not kind or start is None or end is None:
            continue
        rank, _, area = ("", "", "") if kind == _APPLY_WHOLE else kind.partition(" ")
        areas = groups.setdefault((rank, start, max(start, end)), [])
        if area and area not in areas:
            areas.append(area)
    out: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for (rank, start, end), areas in groups.items():
        title = f"{rank} {_APPLY_SUFFIX}" if rank else _APPLY_SUFFIX
        if areas:
            title += f"({'·'.join(areas)})"
        if title in seen:
            continue
        seen.add(title)
        out.append((title, start, end))
    return out


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
    for title, start, end in apply_groups(cx.apply_dates):
        if end >= asof:  # 접수가 끝나지 않았다(접수 중이면 기한 = 지난 시작일이어도 둔다)
            period = start if start == end else f"{start}~{end}"
            want(APPLY_KIND, title, start, f"자동: 청약홈 청약 일정 {period}")
    dated(WINNER_KIND, WINNER_KIND, _day(cx.winner_date), "자동: 청약홈 당첨자 발표일")
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


def _is_auto_key(key: str) -> bool:
    """동기화가 만드는 자동 항목의 키인가(사람이 만든 항목·'사실 재확인'은 'title:' 키)."""
    return not key.startswith("title:")


def _close_auto(it: ChecklistItem, res: ChecklistSync) -> None:
    it.status, it.closed_by = "na", "auto"
    res.closed += 1


def sync_checklist(session: Session, region_id: int, *, asof_date: str) -> ChecklistSync:
    """지역 단지들의 체크리스트 항목을 사실 테이블과 맞춘다(강등 오버레이 적용). flush 만 한다(commit 은 호출자)."""
    from app.analysis.complex_input import masked
    from app.api.demotion import sync_demotions
    from app.facts_view import load_overlay

    res = ChecklistSync()
    complexes = list(
        session.scalars(select(Complex).where(Complex.region_id == region_id).order_by(Complex.id))
    )
    ids = [c.id for c in complexes]
    if ids:
        sync_demotions(session, set(ids))  # 강등 복원 기록·'사실 재확인' 재오픈(쓰기 경로)
    overlay = load_overlay(session, complex_ids=ids) if ids else None
    terms: dict[int, list[PaymentTerms]] = defaultdict(list)
    if ids:
        for t in session.scalars(select(PaymentTerms).where(PaymentTerms.complex_id.in_(ids))):
            fields = overlay.fields("payment_terms", t.id) if overlay is not None else frozenset()
            terms[t.complex_id].append(masked(t, fields))
    estimated = _estimated(session, ids)
    existing: dict[tuple[int | None, str], list[ChecklistItem]] = defaultdict(list)
    if ids:
        for it in session.scalars(
            select(ChecklistItem).where(ChecklistItem.complex_id.in_(ids)).order_by(ChecklistItem.id)
        ):
            existing[(it.complex_id, item_key(it.kind, it.title))].append(it)
    by_complex: dict[int | None, list[tuple[str, list[ChecklistItem]]]] = defaultdict(list)
    for (cid, key), group in existing.items():
        by_complex[cid].append((key, group))
    absorbed = absorbed_remnant_rows(session, region_id)
    for cx in complexes:
        if excluded_for_checklist(cx) or cx.id in absorbed:
            for key, group in by_complex.get(cx.id, []):
                if not _is_auto_key(key):
                    continue  # 사람이 만든 항목은 사람이 닫는다(R3 4차 minor — 단지 제외로 auto 로 닫히던 것)
                for it in group:
                    if it.status == "open" and it.kind not in PROTECTED_KINDS:
                        _close_auto(it, res)
            continue
        demoted = overlay.fields("complex", cx.id) if overlay is not None else frozenset()
        est = {k: v for k, v in estimated.get(cx.id, {}).items() if k not in demoted}
        wants = _wants(masked(cx, demoted), terms.get(cx.id, []), est, asof_date)
        wanted_keys = {w.key for w in wants}
        for w in wants:
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
                auto = [i for i in group if i.status == "na" and i.closed_by == "auto"]
                if not auto:
                    res.unchanged += 1  # 사람이 처리한 done·na 는 고치지 않는다
                    continue
                keep = auto[-1]  # 동기화가 닫은 항목 — 근거가 돌아왔다(재포함·강등 해제·값 복구) → 다시 연다
                keep.status, keep.closed_by = "open", None
                keep.kind, keep.title, keep.due_date = w.kind, w.title, w.due_date
                res.reopened += 1
                continue
            keep = next((i for i in opens if i.title == w.title), opens[-1])
            for extra in opens:
                if extra is not keep:  # 옛 버전이 남긴 같은 키의 열린 항목
                    _close_auto(extra, res)
            if (keep.kind, keep.title, keep.due_date) != (w.kind, w.title, w.due_date):
                keep.kind, keep.title, keep.due_date = w.kind, w.title, w.due_date
                res.updated += 1
            else:
                res.unchanged += 1
        # 근거 사실이 사라졌거나 강등된 자동 항목(열린 것) → 동기화가 닫는다(M-9). 지난 날짜 항목은 그대로 둔다
        for key, group in by_complex.get(cx.id, []):
            if key in wanted_keys or not _is_auto_key(key):
                continue
            for it in group:
                if it.status == "open" and it.kind not in PROTECTED_KINDS and not _past(it, asof_date):
                    _close_auto(it, res)
    session.flush()
    return res


def _past(it: ChecklistItem, asof_date: str) -> bool:
    """기준일 전에 끝난 날짜 항목 — 근거가 '지난 일정'이라 원하지 않게 된 것이지 사라진 것이 아니다."""
    return it.due_date is not None and it.due_date < asof_date


def sync_checklist_for(session: Session, complex_ids: list[int], *, asof_date: str | None = None) -> None:
    """단지들이 속한 지역마다 ``sync_checklist``(강등·복원·사람 확인 직후 — 쓰기 경로). 기준일 = 오늘(KST)."""
    from app.core.time import today_kst

    ids = sorted({i for i in complex_ids if i is not None})
    if not ids:
        return
    day = asof_date or today_kst().isoformat()
    regions = sorted(
        {r for (r,) in session.execute(select(Complex.region_id).where(Complex.id.in_(ids)).distinct())}
    )
    for rid in regions:
        sync_checklist(session, rid, asof_date=day)
