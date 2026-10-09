"""모든 수치 → ``Fact {v, label, prov, checked_at}`` (RA §4-1, contracts/schemas/fact.json, T13).

- 사실 테이블의 값은 field_provenance 의 chosen 행(entity, entity_id, field)으로 라벨·출처·확인일을 붙인다
  (WP2 ``normalize.provenance`` 와 같은 키). prov = ``fp_<id>``.
- 값이 있는데 출처 행이 없으면(T13): ENV=dev → ``ContractViolation``(500 contract_violation),
  ENV=prod → 라벨 '확인 불가', reason '출처 누락', 값·prov 없이 내보내고 경고 로그.
- 값이 없으면 '확인 불가' + 사유(출처 행의 reason, 없으면 '값 없음'). 빈 라벨은 없다.
- 파생 값(점수·판정기 확률·산술)은 그 원천의 prov(sc_·st_·jl_·hc_·rd_·cs_)를 쓴다.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Iterator, Mapping
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, NamedTuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import ContractViolation
from app.core.logging import get_logger
from app.core.settings import Settings, get_settings
from app.models import FieldProvenance

__all__ = [
    "LABEL_UNKNOWN",
    "FactMaker",
    "ProvIndex",
    "ProvRef",
    "day",
    "fact",
    "num",
    "round2",
    "unknown",
    "weakest",
]

log = get_logger("app.api.facts")

LABEL_UNKNOWN = "확인 불가"
MISSING_REASON = "출처 누락"
DEMOTION_REASON = "검증 모순"  # app.facts_view.DEMOTION_REASON (D10-3·D11-3)
# 라벨 강도(약한 쪽이 이긴다): 산술로 묶을 때 결과 라벨
_ORDER = {"확인됨": 0, "재가공": 1, "비공식": 2, "추정": 3, LABEL_UNKNOWN: 4}

Fact = dict[str, Any]


def num(value: Any) -> Any:
    """Decimal → int(정수면)/float. 그 밖은 그대로."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    return value


def round2(value: Decimal | float | None) -> float | None:
    """표시값: 소수 2자리 ROUND_HALF_UP(4.995 → 5.00, 4.605 → 4.61)."""
    if value is None:
        return None
    d = value if isinstance(value, Decimal) else Decimal(str(value))
    return float(d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def day(value: str | None) -> str | None:
    """확인일 'YYYY-MM-DD'(ISO 시각이면 날짜만)."""
    if not value:
        return None
    text = str(value)[:10]
    return text if len(text) == 10 and text[4] == "-" and text[7] == "-" else None


def weakest(labels: Iterable[str]) -> str:
    items = list(labels)
    return max(items, key=lambda lb: _ORDER.get(lb, 3)) if items else LABEL_UNKNOWN


def fact(
    v: Any,
    label: str,
    prov: str | None,
    checked_at: str | None,
    *,
    reason: str | None = None,
    unit: str | None = None,
    human: bool = False,
) -> Fact:
    """Fact dict. label≠'확인 불가'인데 v·prov 가 없으면 '확인 불가'(값 없음/출처 누락)로 바꾼다."""
    v = num(v)
    if label != LABEL_UNKNOWN and v is None:
        return unknown(reason or "값 없음", checked_at, unit=unit)
    out: Fact = {
        "v": None if label == LABEL_UNKNOWN else v,
        "label": label,
        "prov": prov,
        "checked_at": day(checked_at),
    }
    if label == LABEL_UNKNOWN:
        out["reason"] = (reason or "값 없음")[:120]
    elif reason:
        out["reason"] = reason[:120]
    if unit:
        out["unit"] = unit
    if human:
        out["human"] = True
    if label != LABEL_UNKNOWN and not prov:
        # 출처 없는 수치: dev 만 예외, prod 는 '확인 불가(출처 누락)' + 경고 로그(errors.py 규칙, R3 minor 38)
        detail = f"Fact without prov (label {label})"
        if get_settings().env == "dev":
            raise ContractViolation(detail)
        log.warning("출처 누락: %s", detail, extra={"label": label})
        return unknown(MISSING_REASON, checked_at, unit=unit)
    return out


def unknown(
    reason: str, checked_at: str | None = None, *, unit: str | None = None, prov: str | None = None
) -> Fact:
    out: Fact = {
        "v": None,
        "label": LABEL_UNKNOWN,
        "reason": reason[:120],
        "prov": prov,
        "checked_at": day(checked_at),
    }
    if unit:
        out["unit"] = unit
    return out


class ProvRef(NamedTuple):
    """field_provenance chosen 행에서 Fact 에 쓰는 열만(불변 튜플 — 만들기가 frozen dataclass 보다 싸다).

    목록 화면 성능 — ORM 객체를 만들지 않는다(R3 W8·T16)."""

    id: int
    label: str
    checked_at: str | None
    reason: str | None
    url: str | None
    raw_document_id: int | None
    value_norm: str | None = None


class _ChosenView(Mapping[tuple[str, int, str], Any]):
    """ProvIndex 행 → ``facts_view.ChosenRef`` 를 꺼낼 때만 만드는 보기(강등 오버레이 판단용)."""

    def __init__(self, rows: dict[tuple[str, int, str], ProvRef]) -> None:
        self._rows = rows

    def __getitem__(self, key: tuple[str, int, str]) -> Any:
        from app.facts_view import ChosenRef

        r = self._rows[key]
        return ChosenRef(r.id, r.value_norm, r.reason, r.raw_document_id)

    def __contains__(self, key: object) -> bool:
        return key in self._rows

    def __iter__(self) -> Iterator[tuple[str, int, str]]:
        return iter(self._rows)

    def __len__(self) -> int:
        return len(self._rows)


class ProvIndex:
    """field_provenance chosen 행 색인 (entity, entity_id, field) → 행. 목록 화면은 한 번에 읽는다.

    읽은 행의 강등(검증 모순) 오버레이도 같이 계산한다(``app.facts_view``, D11-3) — ``demoted`` 인
    필드는 Fact 가 '확인 불가(검증 모순)'이다. 읽기 전용(DB 쓰기 없음)."""

    def __init__(self) -> None:
        self._rows: dict[tuple[str, int, str], ProvRef] = {}
        self._loaded: set[tuple[str, int]] = set()
        self._demoted: set[tuple[str, int, str]] = set()

    def load(
        self, session: Session, entity: str, ids: Iterable[int], *, fields: Collection[str] | None = None
    ) -> ProvIndex:
        """``fields`` 를 주면 그 필드 출처만 읽는다(목록 화면). 그때는 읽음 표시를 하지 않아 나중 전체
        읽기가 다시 읽는다."""
        from app.facts_view import load_overlay

        want = sorted({i for i in ids if (entity, i) not in self._loaded})
        fp = FieldProvenance
        cols = (
            fp.entity_id, fp.field, fp.id, fp.label, fp.checked_at, fp.reason, fp.url, fp.raw_document_id,
            fp.value_norm,
        )  # fmt: skip
        for start in range(0, len(want), 500):
            chunk = want[start : start + 500]
            stmt = (
                select(*cols)
                .where(fp.entity == entity, fp.entity_id.in_(chunk), fp.chosen.is_(True))
                .order_by(fp.id)
            )
            if fields is not None:
                stmt = stmt.where(fp.field.in_(sorted(fields)))
            for entity_id, field, fid, label, checked, reason, url, raw_id, vn in session.execute(stmt):
                if entity_id is None:
                    continue
                key = (entity, entity_id, field)
                if key not in self._rows:
                    self._rows[key] = ProvRef(fid, label, checked, reason, url, raw_id, vn)
            if fields is None:
                self._loaded.update((entity, i) for i in chunk)
        if want:
            overlay = load_overlay(session, entity=entity, ids=want, chosen=_ChosenView(self._rows))
            self._demoted.update(overlay.active)
        return self

    def get(self, entity: str, entity_id: int | None, field: str) -> ProvRef | None:
        if entity_id is None:
            return None
        return self._rows.get((entity, entity_id, field))

    def demoted(self, entity: str, entity_id: int | None, field: str) -> bool:
        """강등(검증 모순) 오버레이가 적용 중인 사실 필드인가(D11-3)."""
        return entity_id is not None and (entity, entity_id, field) in self._demoted

    def demoted_fields(self, entity: str, entity_id: int | None) -> frozenset[str]:
        if entity_id is None:
            return frozenset()
        return frozenset(f for (e, i, f) in self._demoted if e == entity and i == entity_id)


class FactMaker:
    """설정(ENV)·출처 색인을 들고 Fact 를 만든다. dev 는 출처 누락을 예외로, prod 는 라벨로."""

    def __init__(self, settings: Settings, prov: ProvIndex | None = None) -> None:
        self.env = settings.env
        self.prov = prov or ProvIndex()

    # ---------------------------------------------------------------- 사실 테이블 필드

    def missing(self, entity: str, entity_id: int | None, field: str, unit: str | None = None) -> Fact:
        detail = f"{entity} {entity_id} field {field} has no field_provenance row (출처 누락)"
        if self.env == "dev":
            raise ContractViolation(detail)
        log.warning("출처 누락: %s", detail, extra={"entity": entity, "entity_id": entity_id, "field": field})
        return unknown(MISSING_REASON, None, unit=unit)

    def field(
        self,
        entity: str,
        entity_id: int | None,
        field: str,
        value: Any,
        *,
        unit: str | None = None,
        prov_field: str | None = None,
    ) -> Fact:
        """DB 값 + chosen 출처 행 → Fact. ``prov_field`` 는 출처 행 이름이 컬럼과 다를 때.
        강등 중(D11-3)이면 값과 무관하게 '확인 불가(검증 모순)'."""
        fp = self.prov.get(entity, entity_id, prov_field or field)
        if self.prov.demoted(entity, entity_id, prov_field or field):
            keep = f"fp_{fp.id}" if fp is not None and (fp.url or fp.raw_document_id) else None
            return unknown(DEMOTION_REASON, fp.checked_at if fp is not None else None, unit=unit, prov=keep)
        value = num(value)
        if value is None:
            if fp is None:
                return unknown("값 없음", None, unit=unit)
            reason = fp.reason or "값 없음"
            keep = f"fp_{fp.id}" if (fp.url or fp.raw_document_id) else None
            return unknown(reason, fp.checked_at, unit=unit, prov=keep)
        if fp is None or fp.label == LABEL_UNKNOWN:
            return self.missing(entity, entity_id, prov_field or field, unit)
        return fact(value, fp.label, f"fp_{fp.id}", fp.checked_at, reason=fp.reason, unit=unit)

    def derived(
        self,
        value: Any,
        sources: list[Fact],
        *,
        reason: str = "산술",
        unit: str | None = None,
        label: str | None = None,
    ) -> Fact:
        """산술 값(현재 구매가 중앙·전매 종료일 등): 원천 Fact 가 하나라도 확인 불가면 그 사유로 확인 불가.
        라벨은 '추정'(또는 지정), prov 는 첫 원천의 prov."""
        for src in sources:
            if src["label"] == LABEL_UNKNOWN:
                return unknown(src.get("reason") or "값 없음", src.get("checked_at"), unit=unit)
        if value is None or not sources:
            return unknown("값 없음", None, unit=unit)
        checked = max((s["checked_at"] for s in sources if s.get("checked_at")), default=None)
        return fact(value, label or "추정", sources[0]["prov"], checked, reason=reason, unit=unit)

    def combine(self, value: Any, sources: list[Fact], *, unit: str | None = None) -> Fact:
        """합(가격 = 공급가 + 발코니 + 옵션): 라벨은 원천 중 가장 약한 것, prov 는 첫 원천."""
        for src in sources:
            if src["label"] == LABEL_UNKNOWN:
                return unknown(src.get("reason") or "값 없음", src.get("checked_at"), unit=unit)
        if value is None or not sources:
            return unknown("값 없음", None, unit=unit)
        label = weakest(s["label"] for s in sources)
        checked = max((s["checked_at"] for s in sources if s.get("checked_at")), default=None)
        reasons = [s["reason"] for s in sources if s.get("reason") and s["label"] == label]
        return fact(
            value, label, sources[0]["prov"], checked, reason=reasons[0] if reasons else None, unit=unit
        )


def facts_ok(facts: Mapping[str, Fact]) -> bool:
    return all(f["label"] != LABEL_UNKNOWN for f in facts.values())
