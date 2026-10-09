"""벤치마크 조립 (R3 C1, DECISIONS D9-2) — 청약홈 과거 공고 분양가 + 입주 후 실거래 → ``benchmark`` 행 + 출처.

벤치마크 = 같은 생활권에서 입주가 끝난(입주예정월 ≤ 기준월) 민영 아파트 중 다음 둘을 모두 가진 단지.

(a) 분양가: 청약홈 공식 API 과거 공고(``collectors/applyhome`` ``fetch_history`` 가 받은 APT 상세 목록 +
    주택형별 원문)의 **84㎡에 가장 가까운 주택형 최고가**(``analysis.price.judge_type`` 과 같은 규칙, 라벨 확인됨).
    언론 역산 분양가(추정)는 아직 원천이 없다(보고 '하지 않은 것').
(b) 입주 후 실거래: ``rtms_trade`` 중 전용 80~85㎡ · 해제 제외 · 입주월 이후. 범위(low·median·high)·건수는
    기준월까지 최근 12개월 창(입주월이 더 늦으면 입주월부터), 고점(peak)은 입주월 이후 받은 전체 거래.
    같은 단지에 Open API 행이 있으면 재가공 행은 쓰지 않는다(rtms_trade 규칙).

단지 매칭 = 정규화한 단지명 + 법정동(문자열 처리 — 판단 아님). 공고 주소 → 법정동(``living_area.assign_legal_dong``),
실거래 → 법정동 코드(있으면) 또는 원문 조회 주소의 LAWD_CD + 동 이름(umdNm). 이름은 같거나(정확) 한쪽이 다른
쪽을 포함(4자 이상)해야 하고, 포함 매칭은 사용승인 연도(buildYear)가 입주예정 연도 ±1 이어야 한다. 후보가 둘 이상이면
매칭하지 않고 '확인 불가(매칭 모호)'로 기록한다(``BenchmarkBuild.unmatched`` → 잡 stats).

sale_period = 분양(모집공고) 연도 ≥ 기준연도 − 3 → '고가 분양기', 그 전 → '저가 분양기' (라벨 추정, 식은 note).
분양권 거래(입주 전, ``rtms_trade.is_presale``)만 있는 단지는 ``is_presale=true`` 행(점수 제외).
생활권 자체 표본(분양권 제외)이 0이면 지역 전체 표본을 그 생활권 행으로 복사한다(라벨 추정, note
'추정(대체: 지역 전체)'). 지역 전체도 0이면 행이 없다 → RA §6-4대로 benchmark 성분 미계산(종합 미계산).

이 모듈이 만든 행은 note 머리표 ``[bm:<주택관리번호>:<공고번호>(:<생활권>)]`` 로 알아본다. 다시 돌리면 같은 행을
갱신하고(멱등), 더 이상 나오지 않는 자기 행만 지운다(그 출처 행은 chosen=false — 출처 행은 지우지 않는다).
머리표가 없는 행(사람·devseed 입력)은 건드리지 않는다.
"""

# ruff: noqa: E501  (한국어 docstring·발췌 문구)

from __future__ import annotations

import json
import re
import statistics
import unicodedata
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.price import judge_type
from app.analysis.types import Label, weakest_label
from app.core.contracts_gen import ProvenanceRow
from app.core.paths import resolve_raw_path
from app.models import Benchmark, FieldProvenance, LegalDong, RawDocument, Region, RtmsTrade
from app.normalize._text import area_from_long_code
from app.normalize.fields import norm_value
from app.normalize.living_area import assign_legal_dong, living_area_of
from app.normalize.provenance import upsert_provenance
from app.normalize.region_resolve import LegalRow

__all__ = [
    "BENCHMARK_FIELDS",
    "BENCHMARK_TAG",
    "RECENT_SALE_YEARS",
    "TRADE_WINDOW_MONTHS",
    "BenchmarkBuild",
    "add_months_ym",
    "build_benchmarks",
    "json_object_at",
    "normalize_apt_name",
    "read_raw_row",
    "sale_period",
]

BENCHMARK_TAG: Final = "[bm:"
BENCHMARK_FIELDS: Final = (
    "sale_price_84_won",
    "sale_year",
    "completed_year",
    "trade_low_won",
    "trade_median_won",
    "trade_high_won",
    "n_trades",
    "peak_won",
    "peak_ym",
)
TRADE_AREA_MIN: Final = Decimal(80)
TRADE_AREA_MAX: Final = Decimal(85)
TRADE_WINDOW_MONTHS: Final = 12
RECENT_SALE_YEARS: Final = 3  # sale_period 경계(D9-2) = analysis.score 의 '최근 3년 분양 사례' 와 같은 수
MIN_CONTAIN_LEN: Final = 4
SUBSTITUTE_NOTE: Final = "추정(대체: 지역 전체)"
AMBIGUOUS: Final = "확인 불가(매칭 모호)"
PRESUBSCRIPTION_SECD: Final = "09"  # 민간사전청약 — 본청약 공고가 다시 나온다(supply.py 와 같은 규칙)
_API_LIST_PATH: Final = "getAPTLttotPblancDetail"
_API_MODEL_PATH: Final = "getAPTLttotPblancMdl"
_LAWD_RE: Final = re.compile(r"[?&]LAWD_CD=(\d{5})")
_TOKEN_SPLIT: Final = re.compile(r"[\s(),\[\]/·]+")


# ---------------------------------------------------------------- 공용 작은 도구 (remaining·checklist 도 쓴다)


def normalize_apt_name(name: str) -> str:
    """단지명 정규화(문자열 처리만): NFKC·소문자, 괄호 안(회차·블록 설명) 제거, '<영문><숫자>블록'·'<숫자>BL' 제거,
    한글·영문·숫자 밖 문자 제거. '힐스테이트 레이크 송도 2차' == '힐스테이트레이크송도2차'."""
    s = unicodedata.normalize("NFKC", name).lower()
    s = re.sub(r"\([^)]*\)|\[[^\]]*\]", "", s)
    s = re.sub(r"[a-z]{0,3}\d+(?:-\d+)?\s*(?:블록|bl)", "", s)
    return re.sub(r"[^0-9a-z가-힣]", "", s)


def sale_period(sale_year: int, asof_year: int) -> tuple[str, str]:
    """(라벨, 식). 분양 연도 ≥ 기준연도 − 3 → 고가 분양기(D9-2, 라벨 추정)."""
    if sale_year >= asof_year - RECENT_SALE_YEARS:
        return "고가 분양기", f"분양 {sale_year} ≥ {asof_year}−{RECENT_SALE_YEARS} → 고가 분양기"
    return "저가 분양기", f"분양 {sale_year} < {asof_year}−{RECENT_SALE_YEARS} → 저가 분양기"


def add_months_ym(ym: str, months: int) -> str:
    """'2026-10' + (−11) → '2025-11'."""
    y, m = int(ym[:4]), int(ym[5:7])
    total = y * 12 + (m - 1) + months
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def read_raw_row(row: RawDocument) -> str | None:
    """원문 파일(UTF-8, 안 되면 cp949). 실패 행·파일 없음이면 None."""
    for rel in (row.text_path, row.path):
        if not rel:
            continue
        try:
            data = resolve_raw_path(rel).read_bytes()
        except (OSError, ValueError):
            continue
        for enc in ("utf-8", "cp949"):
            try:
                return data.decode(enc)
            except UnicodeDecodeError:
                continue
    return None


def json_object_at(text: str, key: str, value: str) -> tuple[int, int] | None:
    """평평한 JSON 행 객체 중 ``"key": "value"`` 를 가진 것의 [시작, 끝) 오프셋(발췌용)."""
    m = re.search(rf'"{re.escape(key)}"\s*:\s*"{re.escape(value)}"', text)
    if m is None:
        return None
    start = text.rfind("{", 0, m.start())
    end = text.find("}", m.end())
    if start < 0 or end < 0:
        return None
    return start, end + 1


def api_rows(text: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    rows = data.get("data") if isinstance(data, dict) else None
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def iso_day(value: object) -> str | None:
    """'2021-03-10' · '20210310' → '2021-03-10'."""
    if not isinstance(value, str):
        return None
    d = value.replace("-", "").replace(".", "").strip()
    return f"{d[:4]}-{d[4:6]}-{d[6:]}" if len(d) == 8 and d.isdigit() else None


def iso_ym(value: object) -> str | None:
    """'202406' · '2024-06' → '2024-06'."""
    if not isinstance(value, str):
        return None
    d = value.replace("-", "").replace(".", "").strip()
    if len(d) != 6 or not d.isdigit() or not 1 <= int(d[4:]) <= 12:
        return None
    return f"{d[:4]}-{d[4:]}"


def legal_rows_for(session: Session, address: str) -> list[LegalRow]:
    names = sorted({t for t in _TOKEN_SPLIT.split(address) if t})
    return [
        LegalRow(
            code=r.code,
            sido_name=r.sido_name,
            sigungu_name=r.sigungu_name,
            eupmyeondong_name=r.eupmyeondong_name,
            ri_name=r.ri_name,
            full_name=r.full_name,
            sigungu_code=r.sigungu_code,
            active=bool(r.active),
        )
        for r in session.scalars(
            select(LegalDong).where(LegalDong.active.is_(True), LegalDong.eupmyeondong_name.in_(names))
        )
    ]


def address_legal_code(session: Session, address: str | None, scope: set[str]) -> str | None:
    """주소 → 법정동 코드(유일할 때만, 지역 법정동으로 좁힘). ``living_area.assign_legal_dong`` 과 같은 규칙."""
    if not address:
        return None
    return assign_legal_dong(address, legal_rows_for(session, address), scope=scope)


def prov_row(
    *,
    entity: str,
    entity_id: int,
    key: str,
    field_name: str,
    value: Any,
    value_text: str,
    doc: RawDocument,
    label: Label,
    reason: str | None = None,
    excerpt: str | None = None,
    span: tuple[int, int] | None = None,
    observed_on: str | None = None,
) -> ProvenanceRow:
    return ProvenanceRow(
        entity=entity,
        entity_id=entity_id,
        entity_key=key[:64],
        field=field_name,
        value_text=value_text,
        value_norm=norm_value(value),
        raw_document_id=doc.id,
        url=doc.url,
        checked_at=doc.fetched_at[:10],
        observed_on=observed_on,
        label=label,
        reason=reason[:120] if reason else None,
        source_rank=1,
        chosen=True,
        conflict_group=None,
        excerpt=excerpt,
        excerpt_start=span[0] if span else None,
        excerpt_end=span[1] if span else None,
    )


def unchoose_provenance(session: Session, entity: str, entity_id: int) -> None:
    for fp in session.scalars(
        select(FieldProvenance).where(
            FieldProvenance.entity == entity, FieldProvenance.entity_id == entity_id
        )
    ):
        fp.chosen = False


def _won(man: object) -> int | None:
    s = str(man or "").replace(",", "").strip()
    return int(s) * 10_000 if s.isdigit() else None


def _fmt_won(won: int) -> str:
    return f"{won // 10_000:,}만원"


# ---------------------------------------------------------------- 원천 읽기


@dataclass(frozen=True)
class _Notice:
    hm: str
    pb: str
    name: str
    address: str | None
    notice_date: str | None
    move_in_ym: str | None
    housing: str | None
    secd: str | None  # HOUSE_SECD (01 APT·09 민간사전청약·10 신혼희망타운)
    doc: RawDocument
    text: str


@dataclass(frozen=True)
class _SalePrice:
    type_code: str
    won: int
    doc: RawDocument
    excerpt: str
    span: tuple[int, int] | None


def _ok_docs(session: Session, region_id: int, source_kind: str, path_part: str) -> list[RawDocument]:
    return list(
        session.scalars(
            select(RawDocument)
            .where(
                RawDocument.source_kind == source_kind,
                RawDocument.region_id == region_id,
                RawDocument.path.is_not(None),
                RawDocument.http_status == 200,
                RawDocument.url.contains(path_part),
            )
            .order_by(RawDocument.id)
        )
    )


def _notices(session: Session, region_id: int) -> list[_Notice]:
    """지역의 청약홈 API APT 목록 원문 → 공고(같은 공고는 최신 원문)."""
    out: dict[tuple[str, str], _Notice] = {}
    for doc in _ok_docs(session, region_id, "applyhome_list", _API_LIST_PATH):
        text = read_raw_row(doc)
        if text is None:
            continue
        for d in api_rows(text):
            hm, pb = str(d.get("HOUSE_MANAGE_NO") or "").strip(), str(d.get("PBLANC_NO") or "").strip()
            if not hm or not pb:
                continue
            addr = d.get("HSSPLY_ADRES")
            out[(hm, pb)] = _Notice(
                hm=hm,
                pb=pb,
                name=str(d.get("HOUSE_NM") or "").strip(),
                address=str(addr) if addr else None,
                notice_date=iso_day(d.get("RCRIT_PBLANC_DE")),
                move_in_ym=iso_ym(d.get("MVN_PREARNGE_YM")),
                housing=str(d.get("HOUSE_DTL_SECD_NM") or "").strip() or None,
                secd=str(d.get("HOUSE_SECD") or "").strip() or None,
                doc=doc,
                text=text,
            )
    return [out[k] for k in sorted(out)]


def _model_docs(session: Session, region_id: int) -> dict[tuple[str, str], tuple[RawDocument, str]]:
    """주택형별(Mdl) 원문 — (주택관리번호, 공고번호) → (최신 원문, 텍스트). APT 공고만."""
    out: dict[tuple[str, str], tuple[RawDocument, str]] = {}
    for doc in _ok_docs(session, region_id, "applyhome_detail", _API_MODEL_PATH):
        text = read_raw_row(doc)
        if text is None:
            continue
        for d in api_rows(text):
            hm, pb = str(d.get("HOUSE_MANAGE_NO") or "").strip(), str(d.get("PBLANC_NO") or "").strip()
            if hm and pb:
                out[(hm, pb)] = (doc, text)
    return out


def _sale_price(notice: _Notice, models: dict[tuple[str, str], tuple[RawDocument, str]]) -> _SalePrice | None:
    got = models.get((notice.hm, notice.pb))
    if got is None:
        return None
    doc, text = got
    priced: dict[str, int] = {}
    for d in api_rows(text):
        if str(d.get("HOUSE_MANAGE_NO") or "").strip() != notice.hm:
            continue
        ty = str(d.get("HOUSE_TY") or "").strip()
        won = _won(d.get("LTTOT_TOP_AMOUNT"))
        if ty and won:
            priced[ty] = won
    best = judge_type((ty, area_from_long_code(ty)) for ty in priced)
    if best is None:
        return None
    span = json_object_at(text, "HOUSE_TY", best)
    excerpt = (
        text[span[0] : span[1]]
        if span
        else f'"HOUSE_TY":"{best}","LTTOT_TOP_AMOUNT":"{priced[best] // 10_000}"'
    )
    return _SalePrice(best, priced[best], doc, excerpt, span)


# ---------------------------------------------------------------- 실거래 묶음


@dataclass
class _Group:
    name: str  # 정규화 이름
    dong: str  # 법정동 이름(읍면동 + 리)
    sggs: set[str | None] = field(default_factory=set)
    trades: list[RtmsTrade] = field(default_factory=list)

    @property
    def build_year(self) -> int | None:
        years = Counter(t.completed_year for t in self.trades if t.completed_year)
        return years.most_common(1)[0][0] if years else None


def _dong_name(row: LegalDong | LegalRow) -> str:
    return " ".join(p for p in (row.eupmyeondong_name, row.ri_name) if p)


def _trade_groups(session: Session, region_id: int) -> list[_Group]:
    trades = list(
        session.scalars(
            select(RtmsTrade)
            .where(
                RtmsTrade.region_id == region_id,
                RtmsTrade.cancelled.is_(False),
                RtmsTrade.area_m2 >= TRADE_AREA_MIN,
                RtmsTrade.area_m2 <= TRADE_AREA_MAX,
            )
            .order_by(RtmsTrade.deal_date, RtmsTrade.id)
        )
    )
    doc_ids = {t.raw_document_id for t in trades if t.raw_document_id is not None}
    lawd: dict[int, str] = {}
    if doc_ids:
        for rid, url in session.execute(
            select(RawDocument.id, RawDocument.url).where(RawDocument.id.in_(doc_ids))
        ):
            m = _LAWD_RE.search(url or "")
            if m:
                lawd[rid] = m.group(1)
    codes = {t.legal_dong_code for t in trades if t.legal_dong_code}
    by_code = (
        {r.code: r for r in session.scalars(select(LegalDong).where(LegalDong.code.in_(codes)))}
        if codes
        else {}
    )
    groups: dict[tuple[str, str], _Group] = {}
    for t in trades:
        row = by_code.get(t.legal_dong_code) if t.legal_dong_code else None
        sgg: str | None
        if row is not None:
            dong, sgg = _dong_name(row), row.sigungu_code
        else:
            dong = " ".join((t.dong or "").split())
            sgg = t.legal_dong_code[:5] if t.legal_dong_code else lawd.get(t.raw_document_id or -1)
        if not dong:
            continue
        g = groups.setdefault(
            (normalize_apt_name(t.apt_name), dong), _Group(normalize_apt_name(t.apt_name), dong)
        )
        g.sggs.add(sgg)
        g.trades.append(t)
    return list(groups.values())


def _match(
    name: str, dong: str, sgg: str | None, move_in_year: int | None, groups: Sequence[_Group]
) -> list[_Group]:
    """정규화 이름 + 법정동 → 후보 묶음(0·1·여럿)."""
    here = [g for g in groups if g.dong == dong and (sgg is None or sgg in g.sggs or g.sggs <= {None})]
    exact = [g for g in here if g.name == name]
    if len(exact) == 1:
        return exact
    pool = exact or [
        g
        for g in here
        if len(name) >= MIN_CONTAIN_LEN
        and len(g.name) >= MIN_CONTAIN_LEN
        and (g.name in name or name in g.name)
    ]
    if move_in_year is not None:
        pool = [g for g in pool if g.build_year is None or abs(g.build_year - move_in_year) <= 1]
    return pool


# ---------------------------------------------------------------- 조립


@dataclass
class _Case:
    tag: str
    notice: _Notice
    living_area: str
    sale: _SalePrice
    trades: list[RtmsTrade]  # 창 안 거래(가격 범위)
    post: list[RtmsTrade]  # 입주 후(분양권이면 분양권) 전체 — 고점
    window: str
    presale: bool
    label: Label


@dataclass
class BenchmarkBuild:
    """``build_benchmarks`` 결과(잡 stats 로 그대로)."""

    samples: dict[str, int] = field(default_factory=dict)  # 생활권 → 자체 표본(분양권 제외)
    substituted: list[str] = field(default_factory=list)  # 지역 전체로 대체한 생활권
    presale: int = 0
    unmatched: list[dict[str, str]] = field(default_factory=list)  # [{notice_no, name, reason}]
    notices: int = 0  # 지역 안 민영 공고(입주 여부 무관)
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    removed: int = 0

    @property
    def changed(self) -> bool:
        return bool(self.inserted or self.updated or self.removed)

    def stats(self) -> dict[str, Any]:
        return {
            "samples": dict(self.samples),
            "substituted": list(self.substituted),
            "presale": self.presale,
            "notices": self.notices,
            "unmatched_n": len(self.unmatched),
            "unmatched_reasons": dict(Counter(u["reason"] for u in self.unmatched)),
            "unmatched": self.unmatched[:50],
            "inserted": self.inserted,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "removed": self.removed,
        }


def _median_won(values: Iterable[int]) -> int:
    m = Decimal(str(statistics.median(list(values))))
    return int(m.quantize(Decimal(1), ROUND_HALF_UP))


def _peak(trades: Sequence[RtmsTrade]) -> RtmsTrade:
    best = trades[0]
    for t in trades[1:]:
        if t.price_won > best.price_won:
            best = t
    return best


def _cases(session: Session, region: Region, asof_date: str, res: BenchmarkBuild) -> list[_Case]:
    scope = set(region.legal_dong_codes or [])
    asof_ym = asof_date[:7]
    win_start = add_months_ym(asof_ym, -(TRADE_WINDOW_MONTHS - 1))
    models = _model_docs(session, region.id)
    groups = _trade_groups(session, region.id)
    legal_cache: dict[str, LegalDong | None] = {}
    out: list[_Case] = []
    taken: dict[tuple[str, str], _Case] = {}  # 실거래 묶음 → 첫(가장 이른) 공고: 분양가 = 최초 공고

    def skip(n: _Notice, reason: str) -> None:
        res.unmatched.append({"notice_no": n.pb, "name": n.name, "reason": reason})

    for n in sorted(_notices(session, region.id), key=lambda x: (x.notice_date or "9999", x.hm, x.pb)):
        if n.housing != "민영" or n.secd == PRESUBSCRIPTION_SECD:
            continue
        code = address_legal_code(session, n.address, scope)
        if code is None or code not in scope:
            continue  # 지역 밖(또는 주소로 법정동을 못 정함) — 이 지역 벤치마크가 아니다
        la = living_area_of(code, region.living_areas or [])
        if la is None:
            continue
        res.notices += 1
        if n.move_in_ym is None:
            skip(n, "확인 불가(입주예정월 없음)")
            continue
        sale = _sale_price(n, models)
        if sale is None:
            skip(
                n,
                "입주 전(과거 공고 조회 대상 아님)"
                if n.move_in_ym > asof_ym
                else "확인 불가(분양가 원문 없음)",
            )
            continue
        if code not in legal_cache:
            legal_cache[code] = session.get(LegalDong, code)
        lrow = legal_cache[code]
        if lrow is None:
            skip(n, "확인 불가(법정동 표 없음)")
            continue
        move_year = int(n.move_in_ym[:4])
        if n.move_in_ym is None:
            continue
        cands = _match(normalize_apt_name(n.name), _dong_name(lrow), lrow.sigungu_code, move_year, groups)
        presale = n.move_in_ym > asof_ym
        if not cands:
            skip(n, "입주 전(분양권 거래 없음)" if presale else "실거래 없음(매칭 단지 없음)")
            continue
        if len(cands) > 1:
            skip(n, AMBIGUOUS)
            continue
        pool = [t for t in cands[0].trades if t.deal_date[:10] <= asof_date]
        if any(t.source == "openapi" for t in pool):
            pool = [t for t in pool if t.source == "openapi"]
        if presale:
            post = [t for t in pool if t.is_presale]
            start = win_start
            empty_reason = "입주 전(분양권 거래 없음)"
        else:
            post = [t for t in pool if not t.is_presale and t.deal_date[:7] >= n.move_in_ym]
            start = max(win_start, n.move_in_ym)
            empty_reason = "실거래 없음(입주 후 거래 없음)"
        window = [t for t in post if t.deal_date[:7] >= start]
        if not window:
            skip(n, empty_reason if not post else f"실거래 없음(최근 {TRADE_WINDOW_MONTHS}개월 거래 없음)")
            continue
        trade_label: Label = "확인됨" if all(t.source == "openapi" for t in window) else "재가공"
        group_key = (cands[0].name, cands[0].dong)
        prev = taken.get(group_key)
        if prev is not None:
            skip(n, f"중복(같은 실거래 단지 — 앞선 공고 {prev.notice.pb})")
            continue
        out.append(
            _Case(
                tag=f"{BENCHMARK_TAG}{n.hm}:{n.pb}]",
                notice=n,
                living_area=la,
                sale=sale,
                trades=window,
                post=post,
                window=f"{start}~{asof_ym}",
                presale=presale,
                label=weakest_label("확인됨", trade_label),
            )
        )
        taken[group_key] = out[-1]
    return out


def _values(case: _Case, asof_year: int) -> dict[str, Any]:
    prices = [t.price_won for t in case.trades]
    peak = _peak(case.post)
    sale_year = int(case.notice.notice_date[:4]) if case.notice.notice_date else None
    period = sale_period(sale_year, asof_year) if sale_year is not None else None
    return {
        "living_area": case.living_area,
        "name": case.notice.name[:200],
        "completed_year": int(case.notice.move_in_ym[:4]) if case.notice.move_in_ym else None,
        "sale_year": sale_year,
        "sale_period": period[0] if period else None,
        "sale_price_84_won": case.sale.won,
        "sale_price_label": case.label,
        "trade_low_won": min(prices),
        "trade_median_won": _median_won(prices),
        "trade_high_won": max(prices),
        "trade_window": case.window,
        "n_trades": len(prices),
        "peak_won": peak.price_won,
        "peak_ym": peak.deal_date[:7],
        "is_presale": case.presale,
        "_period_formula": period[1] if period else "분양 연도 확인 불가",
    }


def _note(case: _Case, vals: dict[str, Any], tag: str, substitute_for: str | None) -> str:
    kind = "분양권 거래(입주 전)" if case.presale else "입주 후 실거래"
    parts = [
        tag,
        f"{SUBSTITUTE_NOTE} — 생활권 {substitute_for} 자체 표본 0, 원 생활권 {case.living_area}"
        if substitute_for
        else "",
        f"분양가 = 청약홈 공식 API 공고 {case.notice.pb} 주택형 {case.sale.type_code} 최고가(84㎡ 최근접, 확인됨)",
        f"{kind} = rtms 전용 80~85㎡·해제 제외 {case.window} {vals['n_trades']}건(고점 = 입주 후 받은 전체)",
        f"sale_period: {vals['_period_formula']}(라벨 추정)",
    ]
    return " · ".join(p for p in parts if p)


def _write_prov(
    session: Session, row: Benchmark, case: _Case, vals: dict[str, Any], tag: str, sub: bool
) -> None:
    n, sale = case.notice, case.sale
    label: Label = "추정" if sub else case.label
    trade_labels: list[Label] = ["확인됨" if t.source == "openapi" else "재가공" for t in case.trades]
    trade_label: Label = "추정" if sub else weakest_label(*trade_labels)
    sub_reason = "대체: 지역 전체" if sub else None
    win = f"{case.window} 전용 80~85㎡ 해제 제외 {vals['n_trades']}건"
    peak = _peak(case.post)
    median_src = sorted(case.trades, key=lambda t: (t.price_won, t.deal_date))[len(case.trades) // 2]
    low = min(case.trades, key=lambda t: (t.price_won, t.deal_date))
    high = max(case.trades, key=lambda t: (t.price_won, t.deal_date))
    docs = {t.raw_document_id for t in (median_src, low, high, peak) if t.raw_document_id is not None}
    by_id = (
        {d.id: d for d in session.scalars(select(RawDocument).where(RawDocument.id.in_(docs)))}
        if docs
        else {}
    )
    span = json_object_at(n.text, "HOUSE_MANAGE_NO", n.hm)
    notice_ex = n.text[span[0] : span[1]] if span else n.name
    rows = [
        prov_row(
            entity="benchmark", entity_id=row.id, key=tag, field_name="sale_price_84_won", value=sale.won,
            value_text=f"{_fmt_won(sale.won)} ({sale.type_code} 최고가)", doc=sale.doc,
            label="추정" if sub else "확인됨", reason=sub_reason or "84㎡ 최근접 주택형 최고가",
            excerpt=sale.excerpt, span=sale.span, observed_on=n.notice_date,
        ),
        prov_row(
            entity="benchmark", entity_id=row.id, key=tag, field_name="sale_year", value=vals["sale_year"],
            value_text=n.notice_date or "", doc=n.doc, label=label, reason=sub_reason or "모집공고일 연도",
            excerpt=notice_ex, span=span, observed_on=n.notice_date,
        ),
        prov_row(
            entity="benchmark", entity_id=row.id, key=tag, field_name="completed_year", value=vals["completed_year"],
            value_text=n.move_in_ym or "", doc=n.doc, label="추정",
            reason=sub_reason or "입주예정월 연도(준공 연도 대용)", excerpt=notice_ex, span=span,
            observed_on=n.notice_date,
        ),
    ]  # fmt: skip

    def trade_prov(field_name: str, value: Any, t: RtmsTrade, text: str, reason: str) -> None:
        doc = by_id.get(t.raw_document_id) if t.raw_document_id is not None else None
        if doc is None:
            return  # 원문 없는 거래(재구성 자료) — 출처 행을 지어내지 않는다(전수 검사에서 드러난다)
        rows.append(
            prov_row(
                entity="benchmark", entity_id=row.id, key=tag, field_name=field_name, value=value,
                value_text=text, doc=doc, label=trade_label, reason=sub_reason or reason,
                excerpt=f"{t.apt_name} {t.area_m2}㎡ {t.floor}층 {_fmt_won(t.price_won)} {t.deal_date}",
                observed_on=t.deal_date,
            )
        )  # fmt: skip

    trade_prov("trade_low_won", vals["trade_low_won"], low, _fmt_won(low.price_won), f"최저({win})")
    trade_prov(
        "trade_median_won",
        vals["trade_median_won"],
        median_src,
        _fmt_won(vals["trade_median_won"]),
        f"중앙값({win})",
    )
    trade_prov("trade_high_won", vals["trade_high_won"], high, _fmt_won(high.price_won), f"최고({win})")
    trade_prov("n_trades", vals["n_trades"], median_src, f"{vals['n_trades']}건", f"건수({win})")
    trade_prov("peak_won", vals["peak_won"], peak, _fmt_won(peak.price_won), "입주 후 받은 거래 중 최고")
    trade_prov("peak_ym", vals["peak_ym"], peak, vals["peak_ym"], "고점 거래 월")
    upsert_provenance(session, rows)


_COLUMNS: Final = (
    "living_area",
    "name",
    "completed_year",
    "sale_year",
    "sale_period",
    "sale_price_84_won",
    "sale_price_label",
    "trade_low_won",
    "trade_median_won",
    "trade_high_won",
    "trade_window",
    "n_trades",
    "peak_won",
    "peak_ym",
    "is_presale",
    "note",
)


def build_benchmarks(session: Session, region_id: int, *, asof_date: str) -> BenchmarkBuild:
    """지역의 벤치마크 행을 다시 조립한다(멱등). commit 은 호출자."""
    region = session.get(Region, region_id)
    if region is None:
        raise LookupError(f"region {region_id} 없음")
    res = BenchmarkBuild()
    asof_year = int(asof_date[:4])
    cases = _cases(session, region, asof_date, res)
    area_ids = [str(a["id"]) for a in region.living_areas or []]
    own = [c for c in cases if not c.presale]
    res.samples = {la: sum(1 for c in own if c.living_area == la) for la in area_ids}
    res.presale = sum(1 for c in cases if c.presale)

    wanted: list[tuple[str, _Case, dict[str, Any], str | None]] = []
    for c in cases:
        vals = _values(c, asof_year)
        vals["note"] = _note(c, vals, c.tag, None)
        wanted.append((c.tag, c, vals, None))
    if own:
        for la in area_ids:
            if res.samples.get(la):
                continue
            res.substituted.append(la)
            for c in own:
                tag = f"{BENCHMARK_TAG}{c.notice.hm}:{c.notice.pb}:{la}]"
                vals = _values(c, asof_year)
                vals.update(living_area=la, sale_price_label="추정")
                vals["note"] = _note(c, vals, tag, la)
                wanted.append((tag, c, vals, la))

    existing: dict[str, Benchmark] = {}
    for b in session.scalars(
        select(Benchmark).where(Benchmark.region_id == region.id).order_by(Benchmark.id)
    ):
        if b.note and b.note.startswith(BENCHMARK_TAG):
            existing.setdefault(b.note.split("]", 1)[0] + "]", b)
    seen: set[str] = set()
    for tag, case, vals, sub in wanted:
        seen.add(tag)
        row = existing.get(tag)
        cols = {k: vals[k] for k in _COLUMNS}
        if row is None:
            row = Benchmark(region_id=region.id, **cols)
            session.add(row)
            session.flush()
            res.inserted += 1
        elif any(getattr(row, k) != v for k, v in cols.items()):
            for k, v in cols.items():
                setattr(row, k, v)
            session.flush()
            res.updated += 1
        else:
            res.unchanged += 1
        _write_prov(session, row, case, vals, tag, sub is not None)
    for tag, row in existing.items():
        if tag not in seen:
            unchoose_provenance(session, "benchmark", row.id)
            session.delete(row)
            res.removed += 1
    session.flush()
    return res
