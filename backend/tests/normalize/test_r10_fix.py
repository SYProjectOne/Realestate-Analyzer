"""R10-FIX — 같은 원문의 옛 파싱 출처 행이 다른 원문의 정규화에서 다시 채택되던 결함(운영 인천 스냅샷 6·7 ``complex.apply_dates``).

운영 DB(읽기 전용, 2026-10-14): 단지 2 의 ``apply_dates`` 출처 행 4개 — 청약홈 공식 API 원문(rd 13)·웹 상세 원문(rd 15) 각각에
R9-PARSE 전 파서가 남긴 옛 모양 행(``[{kind:'1순위', date}]`` — fp 112·134)과 R9-PARSE 파서가 새로 만든 행(``[{kind, start, end}]``
— fp 27946·27947). 출처 행 갱신(``upsert_provenance``)은 값 표기(value_text)가 다르면 새 행을 만들고 옛 행은 지우지 않는다(chosen
false). 원문 A 를 다시 정규화하면 A 의 옛 행은 '이번 원문'이라 후보에서 빠지지만 **다른 원문 B 의 옛 행은 후보**로 되살아나고(
``store._reparse_existing``), 같은 출처 종류 안에서는 원문 번호가 큰 쪽·같은 원문이면 먼저 만든 행이 이긴다 → 옛 모양으로 바뀜
(이벤트) → B 를 정규화하면 다시 새 모양(이벤트). 매 수집마다 단지당 2건(스냅샷 7: 46 단지 92건).

고친 뒤 규칙(``normalize.store``·``fields.SUPERSEDED_REASON``):

- 원문 R 을 정규화하면 그 원문이 이번에 낸 후보 묶음(엔티티·필드)의 R 출처 행 중 이번 파싱이 다시 만들지 않은 파서 행(판정기
  추출·감사 행 제외)은 '옛 파싱' 표식(reason 머리)·chosen false·conflict_group 없음 — 어느 경로에서도 후보가 아니다.
- 다른 원문 R' 의 같은 묶음 출처 행이 둘 이상이면(옛 파싱이 남았을 수 있음) R' 을 지금 파서로 다시 읽어 지금 파싱과 같은 행만
  후보로 쓰고 나머지는 같은 표식(표식 전 DB — 배포 직후 첫 수집에서도 뒤집히지 않는다). 원문을 못 읽으면 표식하지 않는다(그대로).
"""

# ruff: noqa: E501  (한국어 docstring·발췌)

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.contracts_gen import RawDocument as RawDocumentDTO
from app.models import ChangeEvent, Complex, ComplexType, FieldProvenance, PaymentTerms, Region
from app.normalize import applyhome_api_parser as api_mod
from app.normalize import applyhome_parser as web_mod
from app.normalize import notice_parser as np_mod
from app.normalize.applyhome_api_parser import APPLY_KINDS
from app.normalize.store import store_raw_document

from ._support import FIX, AddRaw

API = FIX / "applyhome_api"
R9 = FIX / "r9_parse"
URLS = {m["file"]: m["url"] for m in json.loads((API / "manifest.json").read_text(encoding="utf-8"))}
TAG = "옛 파싱"  # fields.SUPERSEDED_REASON 의 머리(수정 전 트리에서도 import 오류 없이 돌도록 글자로)


# ---------------------------------------------------------------- 옛 파서(R9-PARSE 전) 모양


def _old_items(found: dict[str, tuple[str, str]]) -> list[dict[str, str]]:
    """R9-PARSE 전 파서: 순위(구분 첫 낱말)마다 시작일 하나 ``{kind, date}`` — 거주지역 구분·마감일 없음."""
    order = {k: i for i, k in enumerate(APPLY_KINDS)}
    firsts: dict[str, str] = {}
    for k in sorted(found, key=lambda k: (order.get(k, len(order)), k)):
        rank = k.split()[0]
        if rank not in firsts or found[k][0] < firsts[rank]:
            firsts[rank] = found[k][0]
    return [{"kind": r, "date": d} for r, d in firsts.items()]


def _old_text(items: list[dict[str, str]]) -> str:
    return "; ".join(f"{a['kind']} {a.get('date') or a.get('start')}" for a in items)


def _use_old_apply_parser(monkeypatch: pytest.MonkeyPatch) -> Callable[[], None]:
    """두 파서(API·웹 상세)를 옛 모양으로. 돌려준 함수가 되돌린다."""
    for mod in (api_mod, web_mod):
        monkeypatch.setattr(mod, "apply_items", _old_items)
        monkeypatch.setattr(mod, "apply_text", _old_text)
    return monkeypatch.undo


def _docs(add_raw: AddRaw, region: Region, no: str = "2026000367") -> list[RawDocumentDTO]:
    """운영과 같은 순서: 공식 API 상세(번호 작음) → 웹 상세(번호 큼). 둘 다 출처 종류 applyhome_detail."""
    api_name = next(n for n in URLS if n.endswith(f"Detail_{no}.json"))
    web_name = f"web_detail_{no}.html"
    return [
        add_raw(
            (API / api_name).read_text(encoding="utf-8"),
            source_kind="applyhome_detail",
            url=URLS[api_name],
            region_id=region.id,
            ext="json",
        ),
        add_raw(
            (API / web_name).read_text(encoding="utf-8"),
            source_kind="applyhome_detail",
            url=URLS[web_name],
            region_id=region.id,
            ext="html",
        ),
    ]


def _store_all(
    db_session: Session, raw_dir: Path, docs: list[RawDocumentDTO], field: str | None = None
) -> list[ChangeEvent]:
    events: list[ChangeEvent] = []
    for d in docs:
        events.extend(store_raw_document(db_session, d, raw_dir=raw_dir).change_events)
        db_session.flush()
    return [e for e in events if field is None or e.field == field]


def _untag(db_session: Session) -> int:
    """수정 전 배포가 남긴 DB 모양으로 되돌린다: 옛 파싱 행에 표식이 없다(수정 전 트리에서는 표식 행이 없어 아무것도 안 한다)."""
    n = 0
    for fp in db_session.scalars(select(FieldProvenance)):
        if (fp.reason or "").startswith(TAG):
            _, sep, rest = (fp.reason or "").partition("; ")
            fp.reason = rest if sep and rest else None
            n += 1
    db_session.flush()
    return n


def _rows(db_session: Session, entity: str, eid: int, field: str) -> list[FieldProvenance]:
    return list(
        db_session.scalars(
            select(FieldProvenance)
            .where(
                FieldProvenance.entity == entity,
                FieldProvenance.entity_id == eid,
                FieldProvenance.field == field,
            )
            .order_by(FieldProvenance.id)
        )
    )


def _state(db_session: Session) -> list[tuple[Any, ...]]:
    """출처 행 전부 + 단지 일정(바이트 비교 — D23-1)."""
    db_session.flush()
    fps = [
        (
            fp.id,
            fp.entity,
            fp.entity_id,
            fp.field,
            fp.value_norm,
            fp.value_text,
            fp.chosen,
            fp.reason,
            fp.conflict_group,
            fp.label,
        )
        for fp in db_session.scalars(select(FieldProvenance).order_by(FieldProvenance.id))
    ]
    cxs = [
        (c.id, json.dumps(c.apply_dates, sort_keys=True))
        for c in db_session.scalars(select(Complex).order_by(Complex.id))
    ]
    return [*fps, *cxs]


# ====================================================================== apply_dates — 두 원문(API·웹 상세)


def test_upgrade_run_writes_one_value_with_one_event(
    db_session: Session, raw_dir: Path, add_raw: AddRaw, region: Region, monkeypatch: pytest.MonkeyPatch
) -> None:
    """옛 파서로 저장된 단지(운영 스냅샷 1~5) → 지금 파서로 한 번 수집(스냅샷 6): 단지 일정은 새 모양 하나로, 이벤트는 그 변경 1건."""
    docs = _docs(add_raw, region)
    restore = _use_old_apply_parser(monkeypatch)
    _store_all(db_session, raw_dir, docs)
    cx = db_session.scalars(select(Complex).where(Complex.applyhome_id == "2026000367")).one()
    old = list(cx.apply_dates)
    assert old and all(set(a) == {"kind", "date"} for a in old), old
    restore()

    events = _store_all(db_session, raw_dir, docs, "apply_dates")
    db_session.refresh(cx)
    assert cx.apply_dates and all(set(a) == {"kind", "start", "end"} for a in cx.apply_dates), cx.apply_dates
    assert len(events) <= 1, [(e.old_text, e.new_text) for e in events]
    assert [json.loads(str(e.new_text)) for e in events] in ([], [cx.apply_dates])
    # 같은 날 다시(같은 순서·거꾸로) — 0 건
    assert _store_all(db_session, raw_dir, docs, "apply_dates") == []
    assert _store_all(db_session, raw_dir, list(reversed(docs)), "apply_dates") == []


@pytest.mark.parametrize("order", ["api_first", "web_first"])
def test_ops_snapshot7_state_rerun_makes_no_apply_dates_events(
    order: str,
    db_session: Session,
    raw_dir: Path,
    add_raw: AddRaw,
    region: Region,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """운영 스냅샷 7 직전 모양(두 원문 모두 옛 모양 행 + 새 모양 행, 표식 없음, 단지 값 = 새 모양)에서 같은 날 수집 → apply_dates
    이벤트 0(수정 전: 단지당 2건 — 새 → 옛 → 새), 최종 값 새 모양, 옛 행은 표식·채택 안 됨·상충 묶음 없음. 한 번 더 → DB 그대로."""
    docs = _docs(add_raw, region)
    restore = _use_old_apply_parser(monkeypatch)
    _store_all(db_session, raw_dir, docs)
    restore()
    _store_all(db_session, raw_dir, docs)
    _untag(db_session)  # 수정 전 배포(R9-PARSE·R10)가 남긴 모양
    cx = db_session.scalars(select(Complex).where(Complex.applyhome_id == "2026000367")).one()
    new = list(cx.apply_dates)
    assert new and all("start" in a for a in new)
    rows = _rows(db_session, "complex", cx.id, "apply_dates")
    assert len(rows) == 4 and sum(1 for r in rows if '"date"' in (r.value_norm or "")) == 2, [
        (r.raw_document_id, r.value_norm) for r in rows
    ]

    run = docs if order == "api_first" else list(reversed(docs))
    events = _store_all(db_session, raw_dir, run, "apply_dates")
    assert events == [], [(e.old_text, e.new_text) for e in events]
    db_session.refresh(cx)
    assert cx.apply_dates == new
    rows = _rows(db_session, "complex", cx.id, "apply_dates")
    stale = [r for r in rows if '"date"' in (r.value_norm or "")]
    fresh = [r for r in rows if r not in stale]
    assert len(stale) == 2 and len(fresh) == 2
    assert all(
        (r.reason or "").startswith(TAG) and not r.chosen and r.conflict_group is None for r in stale
    ), [(r.reason, r.chosen, r.conflict_group) for r in stale]
    assert sum(1 for r in fresh if r.chosen) == 1 and all(r.conflict_group is None for r in fresh)

    s1 = _state(db_session)
    assert _store_all(db_session, raw_dir, docs, "apply_dates") == []
    assert _store_all(db_session, raw_dir, list(reversed(docs)), "apply_dates") == []
    assert _state(db_session) == s1


def test_superseded_rows_are_not_candidates_in_field_reresolve(
    db_session: Session, raw_dir: Path, add_raw: AddRaw, region: Region, monkeypatch: pytest.MonkeyPatch
) -> None:
    """표식된 옛 파싱 행은 저장 경로 밖(사람 확인·가격 다시 보기 ``resolve_field_group``, 판정 결과 반영 ``judged._reresolve``)에서도
    후보가 아니다 — 원문 번호가 큰 웹 상세의 옛 행이 이기지 않는다."""
    from app.normalize.judged import _reresolve
    from app.normalize.store import resolve_field_group

    docs = _docs(add_raw, region)
    restore = _use_old_apply_parser(monkeypatch)
    _store_all(db_session, raw_dir, docs)
    restore()
    _store_all(db_session, raw_dir, docs)
    cx = db_session.scalars(select(Complex).where(Complex.applyhome_id == "2026000367")).one()
    new = list(cx.apply_dates)
    assert resolve_field_group(db_session, "complex", cx.id, "apply_dates", []) == []
    _, evs = _reresolve(
        db_session, "complex", cx.id, "apply_dates", snapshot_id=None, detected_at="2026-10-14T06:00:00+09:00"
    )
    assert evs == []
    db_session.refresh(cx)
    assert cx.apply_dates == new


def test_unreadable_other_document_is_left_as_is(
    db_session: Session, raw_dir: Path, add_raw: AddRaw, region: Region, monkeypatch: pytest.MonkeyPatch
) -> None:
    """다른 원문 파일을 못 읽으면(지금 파싱을 알 수 없음) 그 원문의 출처 행에 표식하지 않는다 — 추측으로 지우지 않는다."""
    docs = _docs(add_raw, region)
    restore = _use_old_apply_parser(monkeypatch)
    _store_all(db_session, raw_dir, docs)
    restore()
    _store_all(db_session, raw_dir, docs)
    _untag(db_session)
    web = docs[1]
    assert web.path is not None
    (raw_dir / web.path).unlink()
    store_raw_document(db_session, docs[0], raw_dir=raw_dir)
    db_session.flush()
    cx = db_session.scalars(select(Complex).where(Complex.applyhome_id == "2026000367")).one()
    web_rows = [r for r in _rows(db_session, "complex", cx.id, "apply_dates") if r.raw_document_id == web.id]
    assert len(web_rows) == 2 and not any((r.reason or "").startswith(TAG) for r in web_rows)


# ====================================================================== R9-PARSE·R10 이 바꾼 다른 필드 — 같은 두 원문 모양


def test_notice_fields_two_writers_same_day_rerun_is_quiet(
    db_session: Session, raw_dir: Path, add_raw: AddRaw, region: Region, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R9-PARSE 가 바꾼 공고문 필드(필수 옵션 설명·중도금 회차·잔금 비율)도 같은 묶음을 두 원문이 쓰면 같은 결함 모양이다(운영은
    공고문 1건이 한 묶음이라 나타나지 않았다 — 운영 DB: options_text·balance_pct·interim_schedule 묶음의 원문 수 모두 1). 같은 공고문
    두 사본(다시 받은 파일) → 옛 파서 → 지금 파서 → (표식 없는 수정 전 모양) → 같은 날 다시: 이벤트 0, 값은 지금 파서 값."""
    no = "2025000560"
    text = (R9 / "notice_2025000560_cityociel8.txt").read_text(encoding="utf-8")
    base = f"https://static.applyhome.co.kr/ai/aia/getAtchmnfl.do?houseManageNo={no}&pblancNo={no}&atchmnflSeqNo=1&atchmnflSn="
    docs = [
        add_raw(text, source_kind="notice_pdf", url=base + "1", region_id=region.id),
        add_raw(text + "\n", source_kind="notice_pdf", url=base + "2", region_id=region.id),
    ]
    real = np_mod.parse_notice_text

    def old_parser(t: str, raw: Any) -> list[Any]:  # R9-PARSE 전 파서가 낸 값(test_r9_parse 와 같은 모양)
        out = []
        for c in real(t, raw):
            if c.field == "options_text":
                c = c.model_copy(
                    update={"value": "상기 공급금액에는 … 미포함된 가격이며", "value_text": "고지문"}
                )
            if c.field == "interim_schedule":
                c = c.model_copy(
                    update={
                        "value": '[{"due_date":"2028-12-07","pct":35.0,"seq":2}]',
                        "value_text": "2회차 35%",
                    }
                )
            if c.field == "balance_pct":
                c = c.model_copy(update={"value": "30", "value_text": "30%"})
            out.append(c)
        return out

    monkeypatch.setattr(np_mod, "parse_notice_text", old_parser)
    _store_all(db_session, raw_dir, docs)
    monkeypatch.setattr(np_mod, "parse_notice_text", real)
    upgrade = _store_all(db_session, raw_dir, docs)
    watched = {"options_text", "interim_schedule", "balance_pct"}
    per_row: dict[tuple[str, int | None, str], int] = {}
    for e in upgrade:
        if e.field in watched:
            per_row[(e.entity, e.entity_id, e.field)] = per_row.get((e.entity, e.entity_id, e.field), 0) + 1
    assert per_row and max(per_row.values()) == 1, per_row  # 한 수집 = 실제 변경마다 1건
    _untag(db_session)
    pt = db_session.scalars(select(PaymentTerms)).one()
    want = (list(pt.interim_schedule), pt.balance_pct)
    opts = {t.type_code: t.options_text for t in db_session.scalars(select(ComplexType))}
    assert want[1] is not None and len(want[0]) == 6 and set(opts.values()) == {None}

    again = [e for e in _store_all(db_session, raw_dir, docs) if e.field in watched]
    assert again == [], [(e.entity, e.field, e.old_text, e.new_text) for e in again]
    db_session.refresh(pt)
    assert (list(pt.interim_schedule), pt.balance_pct) == want
    assert {t.type_code: t.options_text for t in db_session.scalars(select(ComplexType))} == opts
    s1 = _state(db_session)
    assert [e for e in _store_all(db_session, raw_dir, list(reversed(docs))) if e.field in watched] == []
    assert _state(db_session) == s1


def test_change_detection_compares_canonical_json() -> None:
    """JSON 일정 필드의 변경 비교는 정준 JSON(키 순서·공백 무관) — 같은 일정의 다른 표기로 이벤트가 생기지 않는다."""
    from app.normalize.changes import value_change_event

    a = [{"kind": "1순위 해당지역", "start": "2026-10-19", "end": "2026-10-22"}]
    b = [{"end": "2026-10-22", "start": "2026-10-19", "kind": "1순위 해당지역"}]
    kw: dict[str, Any] = {
        "entity": "complex", "entity_id": 1, "field": "apply_dates", "snapshot_id": None, "complex_id": 1,
        "detected_at": "2026-10-14T06:00:00+09:00", "initial": False,
    }  # fmt: skip
    assert value_change_event(old=a, new=b, **kw) is None
    assert value_change_event(old=a, new=[{"kind": "1순위", "date": "2026-10-19"}], **kw) is not None
