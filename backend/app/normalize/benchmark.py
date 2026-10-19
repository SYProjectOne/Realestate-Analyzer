"""벤치마크 조립 (R3 C1, DECISIONS D9-2) — 청약홈 과거 공고 분양가 + 입주 후 실거래 → ``benchmark`` 행 + 출처.

벤치마크 = 같은 생활권에서 입주가 끝난(입주예정월 ≤ 기준월) 민영 아파트 중 다음 둘을 모두 가진 단지.

(a) 분양가: 청약홈 공식 API 과거 공고(``collectors/applyhome`` ``fetch_history`` 가 받은 APT 상세 목록 +
    주택형별 원문)의 **84㎡에 가장 가까운 주택형 최고가**(``analysis.price.judge_type`` 과 같은 규칙, 라벨 확인됨).
    2020년 이전 분양 단지(공고 없음)는 언론 기사 분양가(D31-3, ``normalize.benchmark_news`` — 판정기 P2 추출, 라벨 비공식·추정).
(b) 입주 후 실거래: ``rtms_trade`` 중 전용 80~85㎡ · 해제 제외 · 입주월 이후. 범위(low·median·high)·건수는
    기준월까지 최근 12개월 창(입주월이 더 늦으면 입주월부터), 고점(peak)은 입주월 이후 받은 전체 거래.
    같은 단지에 Open API 행이 있으면 재가공 행은 쓰지 않는다(rtms_trade 규칙).

단지 매칭(D10-5 → D31-2) = 법정동 일치 + 정규화한 단지명 **완전 일치**, 완전 일치가 없을 때만 **이름 끝부분 일치**
(문자열 처리 — 판단 아님). 정규화는 공백·대소문자·문장부호와 잔여 공고 회차 괄호만 지우고 차수·단지·블록 번호는 남긴다.
끝부분 일치 = 공고 이름에서 블록 번호·'(민영주택)'·'본청약' 낱말을 떼고 뒤쪽 낱말들을 이은 키(``LOOSE_MIN_CHARS`` 글자
이상, 긴 것부터)로 실거래 이름이 **끝나는** 것(키 뒤에 다른 말·차수가 더 붙은 이름은 다른 단지일 수 있어 잇지 않는다 —
'더샵 송도 퍼스트' ≠ '더샵송도퍼스트파크2단지'). 둘 다 블록 번호가 있으면 같아야 한다. 후보가 둘 이상이면 매칭 모호.
같은 동에서 한 실거래 이름이 다른 이름의 끝부분이면(같은 단지의 다른 표기) 거래를 합친다(``_aliases``). 매칭 방식은 note 에.
준공연도 근사 매칭은 하지 않는다.
공고 주소 → 법정동(``living_area.assign_legal_dong``), 실거래 → 법정동 코드(있으면) 또는 원문 조회 주소의 LAWD_CD +
동 이름(umdNm). 후보가 둘 이상이면 매칭하지 않고 '확인 불가(매칭 모호)'로 기록한다(``BenchmarkBuild.unmatched``).
지역 시군구 안 주소인데 법정동으로 못 바꾸면 '확인 불가(법정동 변환 실패)'로 기록한다.
84㎡ 최근접 주택형이 전용 80~85㎡ 밖(예: 74㎡만 있는 단지)이면 80~85㎡ 실거래와 비교하지 않고 기록한다.
분양가 라벨(sale_price_label)은 분양가 원천의 라벨이다(청약홈 공식 API = 확인됨, 대체 행 = 추정) — 실거래 라벨은
실거래 출처 행·note 에 따로 둔다.
원문은 같은 URL 의 최신 원문만 읽는다(매일 다시 받은 옛 원문을 다시 읽지 않는다). 법정동·원문 행은 한 번에 읽는다.

sale_period = 분양(모집공고) 연도 ≥ 기준연도 − 3 → '고가 분양기', 그 전 → '저가 분양기' (라벨 추정, 식은 note).
분양권 거래(입주 전, ``rtms_trade.is_presale``)만 있는 단지는 ``is_presale=true`` 행(점수 제외). 입주는 했지만 입주 뒤
일반 거래가 아직 없고 분양권 거래만 있는 단지도 ``is_presale=true`` 행이다(D31-1, note '입주 뒤 일반 거래 아직 없음').
생활권 자체 표본(분양권 제외)이 0이면 지역 전체 표본을 그 생활권 행으로 복사한다(라벨 추정,
``benchmark.substitute=true`` — 계약 2026-10-09.7; note '추정(대체: 지역 전체)'는 사람이 읽는 설명일 뿐 판별에 쓰지 않는다). 지역 전체도 0이면 행이 없다 → RA §6-4대로 benchmark 성분 미계산(종합 미계산).

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

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analysis.price import judge_type
from app.analysis.types import Label, weakest_label
from app.core.contracts_gen import ProvenanceRow
from app.core.logging import get_logger
from app.core.paths import resolve_raw_path
from app.models import Benchmark, FieldProvenance, LegalDong, RawDocument, Region, RtmsTrade, Snapshot
from app.normalize._text import area_from_long_code, strip_supply_round
from app.normalize.archive import archived_notices_many
from app.normalize.benchmark_news import NEWS_TAG, NewsPrice
from app.normalize.fields import norm_value
from app.normalize.living_area import assign_legal_dong, living_area_of
from app.normalize.provenance import upsert_provenance
from app.normalize.region_resolve import LegalRow

log = get_logger("app.normalize.benchmark")

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
_IN_CHUNK: Final = 500  # IN (...) 한 번에 넣는 값 수
SUBSTITUTE_NOTE: Final = "추정(대체: 지역 전체)"
AMBIGUOUS: Final = "확인 불가(매칭 모호)"
LEGAL_FAIL: Final = "확인 불가(법정동 변환 실패)"
SALE_LABEL: Final[Label] = "확인됨"  # 분양가 원천 = 청약홈 공식 API 공고(대체 행은 추정)
PRESUBSCRIPTION_SECD: Final = "09"  # 민간사전청약 — 본청약 공고가 다시 나온다(supply.py 와 같은 규칙)
_API_LIST_PATH: Final = "getAPTLttotPblancDetail"
_API_MODEL_PATH: Final = "getAPTLttotPblancMdl"
_LAWD_RE: Final = re.compile(r"[?&]LAWD_CD=(\d{5})")
_TOKEN_SPLIT: Final = re.compile(r"[\s(),\[\]/·]+")


# ---------------------------------------------------------------- 공용 작은 도구 (remaining·checklist 도 쓴다)


def normalize_apt_name(name: str) -> str:
    """단지명 정규화(문자열 처리만, D10-5): NFKC·소문자, 잔여 공고 회차·공급 구분 괄호 제거, 한글·영문·숫자 밖 문자
    제거. 차수·단지·블록 번호는 남긴다. '힐스테이트 레이크 송도(2차)' == '힐스테이트레이크송도2차',
    'AA13-1블록' != 'AA13-2블록'."""
    # 공급 구분 괄호를 **먼저** 뗀다(R3 5차 minor: NFKC 가 'Ⅱ' 를 'II' 로 바꾼 뒤 지우면 '(Ⅱ 잔여세대)'·'(Ⅲ 잔여세대)'·
    # '(잔여세대)' 가 같은 키였다). 블록 표기 변형('블럭'·'BL')은 '블록' 하나로(같은 블록)
    s = unicodedata.normalize("NFKC", strip_supply_round(name)).lower()
    s = re.sub(r"블럭", "블록", s)
    s = re.sub(r"(?<=\d)\s*bl(?![a-z])", "블록", s)
    # 숫자 사이 하이픈은 남긴다 — 지우면 'AA1-31' 과 'AA13-1' 이 같은 키가 된다(R3 4차 minor)
    s = re.sub(r"(?<=\d)\s*[-‐–]\s*(?=\d)", "-", s)
    return re.sub(r"[^0-9a-z가-힣-]|(?<!\d)-|-(?!\d)", "", s)


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


def _tokens(address: str) -> set[str]:
    return {t for t in _TOKEN_SPLIT.split(address) if t}


def _legal_row(r: LegalDong) -> LegalRow:
    return LegalRow(
        code=r.code,
        sido_name=r.sido_name,
        sigungu_name=r.sigungu_name,
        eupmyeondong_name=r.eupmyeondong_name,
        ri_name=r.ri_name,
        full_name=r.full_name,
        sigungu_code=r.sigungu_code,
        active=bool(r.active),
    )


def legal_rows_for(session: Session, address: str) -> list[LegalRow]:
    names = sorted(_tokens(address))
    return [
        _legal_row(r)
        for r in session.scalars(
            select(LegalDong).where(LegalDong.active.is_(True), LegalDong.eupmyeondong_name.in_(names))
        )
    ]


class LegalIndex:
    """주소 여럿의 법정동 후보를 한 번에 읽어 두는 색인(주소마다 조회하지 않는다 — N+1 없음)."""

    def __init__(self, session: Session, addresses: Iterable[str | None]) -> None:
        names = sorted({t for a in addresses if a for t in _tokens(a)})
        self._by_name: dict[str, list[LegalRow]] = {}
        for i in range(0, len(names), _IN_CHUNK):
            for r in session.scalars(
                select(LegalDong).where(
                    LegalDong.active.is_(True), LegalDong.eupmyeondong_name.in_(names[i : i + _IN_CHUNK])
                )
            ):
                self._by_name.setdefault(r.eupmyeondong_name or "", []).append(_legal_row(r))

    def code(self, address: str | None, scope: set[str]) -> str | None:
        """``address_legal_code`` 와 같은 규칙(미리 읽은 행으로)."""
        if not address:
            return None
        rows = [r for t in sorted(_tokens(address)) for r in self._by_name.get(t, [])]
        return assign_legal_dong(address, rows, scope=scope)


def address_legal_code(session: Session, address: str | None, scope: set[str]) -> str | None:
    """주소 → 법정동 코드(유일할 때만, 지역 법정동으로 좁힘). ``living_area.assign_legal_dong`` 과 같은 규칙."""
    if not address:
        return None
    return assign_legal_dong(address, legal_rows_for(session, address), scope=scope)


def region_sigungu_names(session: Session, scope: set[str]) -> set[str]:
    """지역 법정동의 시군구 이름 토큰('연수구', '김포시') — 법정동 변환 실패를 지역 밖 공고와 가르는 문자열 대조용."""
    sggs = sorted({c[:5] for c in scope})
    if not sggs:
        return set()
    names = session.scalars(select(LegalDong.sigungu_name).where(LegalDong.sigungu_code.in_(sggs)).distinct())
    return {p for n in names if n for p in n.split()}


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
    url: str | None = None,
) -> ProvenanceRow:
    return ProvenanceRow(
        entity=entity,
        entity_id=entity_id,
        entity_key=key[:64],
        field=field_name,
        value_text=value_text,
        value_norm=norm_value(value),
        raw_document_id=doc.id,
        url=url or doc.url,
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


def latest_ok_docs(session: Session, region_id: int, source_kind: str, path_part: str) -> list[RawDocument]:
    """성공 원문 중 URL 마다 최신 1건(id 순). 같은 URL 을 매일 다시 받은 옛 원문은 다시 읽지 않는다."""
    latest = (
        select(func.max(RawDocument.id))
        .where(
            RawDocument.source_kind == source_kind,
            RawDocument.region_id == region_id,
            RawDocument.path.is_not(None),
            RawDocument.http_status == 200,
            RawDocument.url.contains(path_part),
        )
        .group_by(RawDocument.url)
    )
    return list(
        session.scalars(select(RawDocument).where(RawDocument.id.in_(latest)).order_by(RawDocument.id))
    )


def latest_by_urls(session: Session, urls: Iterable[str]) -> dict[str, RawDocument]:
    """URL → 성공 원문 최신 1건. 여러 URL 을 한 번에 읽는다(URL 마다 조회하지 않는다 — N+1 없음)."""
    wanted = sorted(set(urls))
    out: dict[str, RawDocument] = {}
    for i in range(0, len(wanted), _IN_CHUNK):
        for row in session.scalars(
            select(RawDocument)
            .where(
                RawDocument.url.in_(wanted[i : i + _IN_CHUNK]),
                RawDocument.path.is_not(None),
                RawDocument.http_status == 200,
            )
            .order_by(RawDocument.id)
        ):
            out[row.url] = row
    return out


_ok_docs = latest_ok_docs


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


def _archive_price(notice: _Notice, docs: list[RawDocument]) -> _SalePrice | None:
    """분양가 = 자체 아카이브 공고문 우선(RA §3 benchmark, R3 3차 RA 부분 — ``normalize.archive.archived_notices``).

    그 공고(주택관리번호)의 보관 공고문 중 가장 이른 것(최초 공고 = 분양가)의 공급금액 표에서 84㎡ 최근접 주택형 최고가
    (공고문 파서 ``NoticeParser`` — 라벨 확인됨 후보만). 공고문이 없거나 표를 못 읽으면 None → 청약홈 API 주택형 목록."""
    from app.normalize.notice_parser import NoticeParser
    from app.normalize.store import raw_dto

    for doc in docs:  # ``archive.archived_notices_many`` — 오래된 것부터
        try:
            cands = NoticeParser().parse(raw_dto(doc))
        except (
            Exception
        ) as exc:  # 원문 파일 없음 등 — 다음 공고문 또는 API(조용히 넘기지 않는다 — R3 4차 minor)
            log.warning(
                "normalize.benchmark.archive_unreadable",
                extra={"raw_document_id": doc.id, "error": type(exc).__name__},
            )
            continue
        if not cands:
            log.warning("normalize.benchmark.archive_no_candidates", extra={"raw_document_id": doc.id})
        by_type: dict[str, dict[str, Any]] = {}
        for c in cands:
            key = c.entity_key or ""
            if c.entity != "complex_type" or not key.startswith(f"{notice.hm}:") or c.value is None:
                continue
            if c.label != "확인됨":
                continue
            by_type.setdefault(key.split(":", 1)[1], {})[c.field] = c
        priced = {
            str(d["notice_type_code"].value): d["max_price_won"]
            for d in by_type.values()
            if "max_price_won" in d and "notice_type_code" in d
        }
        best = judge_type((ty, area_from_long_code(ty)) for ty in priced)
        if best is None:
            continue
        c = priced[best]
        span = (
            (c.excerpt_start, c.excerpt_end)
            if c.excerpt_start is not None and c.excerpt_end is not None
            else None
        )
        return _SalePrice(best, int(c.value), doc, c.excerpt, span)
    return None


# ---------------------------------------------------------------- 실거래 묶음


@dataclass
class _Group:
    name: str  # 정규화 이름
    dong: str  # 법정동 이름(읍면동 + 리)
    sggs: set[str | None] = field(default_factory=set)
    trades: list[RtmsTrade] = field(default_factory=list)


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


def _same_place(g: _Group, dong: str, sgg: str | None) -> bool:
    return g.dong == dong and (sgg is None or sgg in g.sggs or g.sggs <= {None})


def _match(name: str, dong: str, sgg: str | None, groups: Sequence[_Group]) -> list[_Group]:
    """정규화 이름 완전 일치 + 법정동 → 후보 묶음(0·1·여럿)."""
    return [g for g in groups if g.name == name and _same_place(g, dong, sgg)]


# D31-2: 완전 일치가 없을 때만 쓰는 '이름 끝부분' 매칭(문자열 처리 — 판단 아님). 공고 이름 앞에 붙는 지역 머리말·블록 번호
# ('인천 검단신도시 AB17BL 우미린 클래스원')와 실거래 이름의 다른 머리말('신검단중앙역우미린클래스원')을 잇는다.
LOOSE_MIN_CHARS: Final = 5
"""끝부분 키 최소 글자 수(정규화 뒤) — '더샵'·'자이'·'푸르지오' 같은 브랜드 한 낱말만으로는 잇지 않는다."""
ALIAS_MIN_CHARS: Final = 6
"""같은 동 실거래 표기 합치기(한 이름이 다른 이름의 끝부분)의 짧은 쪽 최소 글자 수."""
_BLOCK_PAREN: Final = re.compile(r"\([^)]*(?:\d\s*(?:블록|블럭|bl)|민영주택|본청약)[^)]*\)", re.IGNORECASE)
_BLOCK_TOKEN: Final = re.compile(r"^(?:[a-z]{1,3}-?\d+(?:-\d+)?(?:블록|bl)?|\d+(?:-\d+)?(?:블록|bl))$")
_GENERIC_TOKENS: Final = frozenset({"민영주택", "본청약"})
_BLOCK_IN_NAME: Final = re.compile(r"[a-z]{0,3}\d+(?:-\d+)?블록")
_PHASE_TAIL: Final = re.compile(r"(?:\d+(?:차|단지)?|(?<![a-z])[ivx]+)$")


def name_tail_keys(name: str) -> list[str]:
    """공고 이름 → 끝부분 키(긴 것부터). 블록 번호·'(민영주택)'·'본청약' 낱말을 떼고, 남은 낱말의 뒤쪽 n개를 이어
    정규화한다. 차수·단지 번호는 남는다(D10-5). 키는 낱말 **두 개 이상**이다 — '호반베르디움'·'대성베르힐' 같은 낱말
    하나(브랜드 이름)만으로는 잇지 않는다. '인천 검단신도시 AB17BL 우미린 클래스원' → ['인천검단신도시우미린클래스원',
    '검단신도시우미린클래스원', '우미린클래스원']."""
    s = unicodedata.normalize("NFKC", strip_supply_round(name)).lower().replace("블럭", "블록")
    s = _BLOCK_PAREN.sub(" ", s)
    toks = [t for t in _TOKEN_SPLIT.split(s) if t and not _BLOCK_TOKEN.match(t) and t not in _GENERIC_TOKENS]
    out: list[str] = []
    for i in range(len(toks) - 1):
        key = normalize_apt_name(" ".join(toks[i:]))
        # 끝의 차수·단지 번호는 글자 수에 세지 않는다('검단iii' 은 '검단' 두 글자 — 키가 아니다)
        if len(_PHASE_TAIL.sub("", key)) >= LOOSE_MIN_CHARS and key not in out:
            out.append(key)
    return out


def block_codes(name: str) -> set[str]:
    """이름 안 블록 번호('aa13-1블록'·'ab17블록') — 정규화 뒤 문자열에서."""
    return set(_BLOCK_IN_NAME.findall(normalize_apt_name(name)))


def _block_conflict(notice_name: str, trade_name: str) -> bool:
    """둘 다 블록 번호가 있는데 겹치는 것이 없다('AA13-1블록' ≠ 'AA13-2블록')."""
    mine, theirs = block_codes(notice_name), block_codes(trade_name)
    return bool(mine and theirs and not mine & theirs)


def tail_matches(trade_name: str, key: str) -> bool:
    """실거래 이름(정규화)이 끝부분 키로 **끝난다**. 키 뒤에 다른 말이 더 붙은 이름('더샵송도퍼스트' →
    '더샵송도퍼스트파크2단지')·차수가 다른 이름('제일풍경채검단i' → '제일풍경채검단ii')은 다른 단지일 수 있어 잇지 않는다."""
    return trade_name.endswith(key)


def _match_tail(
    name: str, dong: str, sgg: str | None, groups: Sequence[_Group]
) -> tuple[list[_Group], str | None]:
    """같은 법정동 실거래 묶음 중 이름이 끝부분 키(긴 것부터)로 끝나는 묶음. 처음 걸린 키의 후보를 돌려준다.
    공고와 실거래 이름 둘 다 블록 번호가 있는데 서로 다르면 후보가 아니다('AA13-1블록' ≠ 'AA13-2블록')."""
    pool = [g for g in groups if _same_place(g, dong, sgg)]
    for key in name_tail_keys(name):
        hits = [g for g in pool if tail_matches(g.name, key) and not _block_conflict(name, g.name)]
        if hits:
            return hits, key
    return [], None


def _aliases(primary: _Group, notice_name: str, sgg: str | None, groups: Sequence[_Group]) -> list[_Group]:
    """같은 법정동에서 한 이름이 다른 이름의 끝부분인 실거래 묶음(같은 단지의 다른 표기 — '검단신도시롯데캐슬넥스티엘'
    분양권 거래와 '롯데캐슬넥스티엘' 입주 뒤 거래). 짧은 쪽이 ``ALIAS_MIN_CHARS`` 글자 이상이고, 공고와 블록 번호가
    어긋나지 않을 때만('청라29블록호반베르디움' 은 A-3블록 공고와 합치지 않는다)."""
    out: list[_Group] = []
    for g in groups:
        if g is primary or not _same_place(g, primary.dong, sgg) or _block_conflict(notice_name, g.name):
            continue
        short, long_ = sorted((g.name, primary.name), key=len)
        if len(short) >= ALIAS_MIN_CHARS and short != long_ and long_.endswith(short):
            out.append(g)
    return out


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
    trade_label: (
        Label  # 창 안 실거래 라벨(Open API 만 = 확인됨, 재가공 섞임 = 재가공) — 분양가 라벨과 섞지 않는다
    )
    match: str = "이름 완전 일치"  # 단지 매칭 방식(note 에 남긴다 — D31-2)
    moved_in_presale: bool = False  # 입주는 했지만 일반 거래 없이 분양권 거래만(D31-1)
    news: NewsPrice | None = None  # 분양가가 언론 기사에서 온 사례(D31-3) — 공고가 없다


@dataclass
class BenchmarkBuild:
    """``build_benchmarks`` 결과(잡 stats 로 그대로)."""

    samples: dict[str, int] = field(default_factory=dict)  # 생활권 → 자체 표본(분양권 제외)
    substituted: list[str] = field(default_factory=list)  # 지역 전체로 대체한 생활권
    presale: int = 0
    unmatched: list[dict[str, str]] = field(default_factory=list)  # [{notice_no, name, reason}]
    notices: int = 0  # 지역 안 민영 공고(입주 여부 무관)
    matched_groups: set[tuple[str, str]] = field(
        default_factory=set
    )  # 공고와 이어진 실거래 묶음(이름, 동) — D31-3 대상 제외
    news: int = 0  # 언론 기사 분양가 사례(D31-3)
    news_skipped: dict[str, int] = field(default_factory=dict)  # 사유 → 수
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
            "news": self.news,
            "news_skipped": dict(self.news_skipped),
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
    notices = [
        n
        for n in sorted(_notices(session, region.id), key=lambda x: (x.notice_date or "9999", x.hm, x.pb))
        if n.housing == "민영" and n.secd != PRESUBSCRIPTION_SECD
    ]
    index = LegalIndex(session, (n.address for n in notices))
    archived = archived_notices_many(session, (n.hm for n in notices), region_id=region.id)
    sgg_names = region_sigungu_names(session, scope)
    codes = sorted({c for n in notices if (c := index.code(n.address, scope)) is not None and c in scope})
    legal_by_code = (
        {r.code: r for r in session.scalars(select(LegalDong).where(LegalDong.code.in_(codes)))}
        if codes
        else {}
    )
    out: list[_Case] = []
    taken: dict[tuple[str, str], _Case] = {}  # 실거래 묶음 → 첫(가장 이른) 공고: 분양가 = 최초 공고

    def skip(n: _Notice, reason: str) -> None:
        res.unmatched.append({"notice_no": n.pb, "name": n.name, "reason": reason})

    for n in notices:
        code = index.code(n.address, scope)
        if code is None:
            if n.address and _tokens(n.address) & sgg_names:
                skip(n, LEGAL_FAIL)  # 지역 시군구 주소인데 법정동을 못 정함 — 소실 없이 기록
            continue  # 그 밖은 지역 밖 공고(시도 단위 목록) — 이 지역 벤치마크가 아니다
        if code not in scope:
            continue
        la = living_area_of(code, region.living_areas or [])
        if la is None:
            continue
        res.notices += 1
        if n.move_in_ym is None:
            skip(n, "확인 불가(입주예정월 없음)")
            continue
        sale = _archive_price(n, archived.get(n.hm, [])) or _sale_price(n, models)
        if sale is None:
            skip(
                n,
                "입주 전(과거 공고 조회 대상 아님)"
                if n.move_in_ym > asof_ym
                else "확인 불가(분양가 원문 없음)",
            )
            continue
        area = area_from_long_code(sale.type_code)
        if area is None or not TRADE_AREA_MIN <= Decimal(str(area)) <= TRADE_AREA_MAX:
            skip(n, f"확인 불가(84㎡대 주택형 없음 — 최근접 {sale.type_code}, 실거래 비교 구간 전용 80~85㎡)")
            continue
        lrow = legal_by_code.get(code)
        if lrow is None:
            skip(n, "확인 불가(법정동 표 없음)")
            continue
        dong, sgg = _dong_name(lrow), lrow.sigungu_code
        cands = _match(normalize_apt_name(n.name), dong, sgg, groups)
        match = "이름 완전 일치"
        if not cands:  # D31-2: 완전 일치가 없을 때만 이름 끝부분
            cands, key = _match_tail(n.name, dong, sgg, groups)
            if key is not None:
                match = f"이름 끝부분 일치('{key}')"
        presale = n.move_in_ym > asof_ym
        res.matched_groups.update((g.name, g.dong) for g in cands)
        if not cands:
            skip(n, "입주 전(분양권 거래 없음)" if presale else "실거래 없음(매칭 단지 없음)")
            continue
        if len(cands) > 1:
            skip(n, AMBIGUOUS)
            continue
        aliases = _aliases(cands[0], n.name, sgg, groups)
        res.matched_groups.update((g.name, g.dong) for g in aliases)
        if aliases:
            match += " + 같은 동 다른 표기 " + "·".join(f"'{g.name}'" for g in aliases)
        merged = sorted(
            (t for g in (cands[0], *aliases) for t in g.trades), key=lambda t: (t.deal_date, t.id)
        )
        pool = [t for t in merged if t.deal_date[:10] <= asof_date]
        if any(t.source == "openapi" for t in pool):
            pool = [t for t in pool if t.source == "openapi"]
        moved_in_presale = False
        if presale:
            post = [t for t in pool if t.is_presale]
            start = win_start
            empty_reason = "입주 전(분양권 거래 없음)"
        else:
            post = [t for t in pool if not t.is_presale and t.deal_date[:7] >= n.move_in_ym]
            start = max(win_start, n.move_in_ym)
            empty_reason = "실거래 없음(입주 후 거래 없음)"
        window = [t for t in post if t.deal_date[:7] >= start]
        if not window and not presale:
            # D31-1: 입주는 했지만 입주 뒤 일반 거래가 아직 없고 분양권 거래만 있으면 분양권 행(점수 제외)
            pre_post = [t for t in pool if t.is_presale]
            pre_window = [t for t in pre_post if t.deal_date[:7] >= win_start]
            if pre_window:
                presale, moved_in_presale = True, True
                post, window, start = pre_post, pre_window, win_start
        if not window:
            skip(n, empty_reason if not post else f"실거래 없음(최근 {TRADE_WINDOW_MONTHS}개월 거래 없음)")
            continue
        trade_label: Label = "확인됨" if all(t.source == "openapi" for t in window) else "재가공"
        keys = [(g.name, g.dong) for g in (cands[0], *aliases)]
        prev = next((taken[k] for k in keys if k in taken), None)
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
                trade_label=trade_label,
                match=match,
                moved_in_presale=moved_in_presale,
            )
        )
        for k in keys:
            taken[k] = out[-1]
    return out


def _news_cases(
    session: Session, region: Region, asof_date: str, prices: Sequence[NewsPrice], res: BenchmarkBuild
) -> list[_Case]:
    """D31-3 언론 기사 분양가 → 사례. 실거래 = 같은 묶음(정규화 이름 + 법정동)의 일반 거래 중 준공 연도 이후·최근 12개월."""
    if not prices:
        return []
    asof_ym = asof_date[:7]
    win_start = add_months_ym(asof_ym, -(TRADE_WINDOW_MONTHS - 1))
    by_key = {(g.name, g.dong): g for g in _trade_groups(session, region.id)}
    docs = {
        d.id: d
        for d in session.scalars(
            select(RawDocument).where(RawDocument.id.in_(sorted({p.raw_document_id for p in prices})))
        )
    }
    out: list[_Case] = []

    def skip(reason: str) -> None:
        res.news_skipped[reason] = res.news_skipped.get(reason, 0) + 1

    for p in sorted(prices, key=lambda x: x.target.key):
        t, doc = p.target, docs.get(p.raw_document_id)
        g = by_key.get((t.norm, t.dong))
        if doc is None or g is None:
            skip("실거래 묶음·기사 원문 없음")
            continue
        if (g.name, g.dong) in res.matched_groups:
            skip("공고와 이어진 단지")
            continue
        pool = [x for x in g.trades if x.deal_date[:10] <= asof_date and not x.is_presale]
        if any(x.source == "openapi" for x in pool):
            pool = [x for x in pool if x.source == "openapi"]
        post = [x for x in pool if int(x.deal_date[:4]) >= t.completed_year]
        start = max(win_start, f"{t.completed_year}-01")
        window = [x for x in post if x.deal_date[:7] >= start]
        if not window:
            skip(f"실거래 없음(최근 {TRADE_WINDOW_MONTHS}개월 거래 없음)")
            continue
        notice = _Notice(
            hm="news", pb=t.key, name=t.name, address=None, notice_date=p.article_date,
            move_in_ym=f"{t.completed_year}-01", housing="민영", secd=None, doc=doc, text=p.excerpt,
        )  # fmt: skip
        out.append(
            _Case(
                tag=f"{NEWS_TAG}{t.key}]",
                notice=notice,
                living_area=t.living_area,
                sale=_SalePrice("기사", p.won, doc, p.excerpt, None),
                trades=window,
                post=post,
                window=f"{start}~{asof_ym}",
                presale=False,
                trade_label="확인됨" if all(x.source == "openapi" for x in window) else "재가공",
                match=f"언론 기사 분양가 대상 = 실거래 이름 '{g.name}'(공고 없음)",
                news=p,
            )
        )
    res.news = len(out)
    return out


def _values(case: _Case, asof_year: int) -> dict[str, Any]:
    prices = [t.price_won for t in case.trades]
    peak = _peak(case.post)
    news = case.news
    if news is not None:
        sale_year: int | None = news.sale_year
    else:
        sale_year = int(case.notice.notice_date[:4]) if case.notice.notice_date else None
    period = sale_period(sale_year, asof_year) if sale_year is not None else None
    return {
        "living_area": case.living_area,
        "name": case.notice.name[:200],
        "completed_year": int(case.notice.move_in_ym[:4]) if case.notice.move_in_ym else None,
        "sale_year": sale_year,
        "sale_period": period[0] if period else None,
        "sale_price_84_won": case.sale.won,
        "sale_price_label": news.label if news is not None else SALE_LABEL,
        "trade_low_won": min(prices),
        "trade_median_won": _median_won(prices),
        "trade_high_won": max(prices),
        "trade_window": case.window,
        "n_trades": len(prices),
        "peak_won": peak.price_won,
        "peak_ym": peak.deal_date[:7],
        "is_presale": case.presale,
        "substitute": False,
        "_period_formula": period[1] if period else "분양 연도 확인 불가",
    }


def _note(case: _Case, vals: dict[str, Any], tag: str, substitute_for: str | None) -> str:
    kind = (
        "분양권 거래(입주 뒤 일반 거래 아직 없음)"
        if case.moved_in_presale
        else "분양권 거래(입주 전)"
        if case.presale
        else "입주 후 실거래"
    )
    parts = [
        tag,
        f"{SUBSTITUTE_NOTE} — 생활권 {substitute_for} 자체 표본 0, 원 생활권 {case.living_area}"
        if substitute_for
        else "",
        f"분양가 = 언론 기사 {case.news.article_date or '날짜 없음'} {case.news.article_url} — {case.news.basis} "
        f"'{case.news.value_text}'(판정기 P2 추출, 라벨 {vals['sale_price_label']}) · {case.news.sale_year_formula}"
        if case.news is not None
        else f"분양가 = {'자체 아카이브 공고문' if case.sale.doc.source_kind == 'notice_pdf' else '청약홈 공식 API'} "
        f"공고 {case.notice.pb} 주택형 {case.sale.type_code} 최고가"
        f"(84㎡ 최근접, 라벨 {vals['sale_price_label']})",
        f"{kind} = rtms 전용 80~85㎡·해제 제외 {case.window} {vals['n_trades']}건(고점 = 입주 후 받은 전체, "
        f"라벨 {'추정' if substitute_for else case.trade_label})",
        f"sale_period: {vals['_period_formula']}(라벨 추정)",
        f"단지 매칭: {case.match} + 법정동",
    ]
    return " · ".join(p for p in parts if p)


def _trade_docs(session: Session, cases: Iterable[_Case]) -> dict[int, RawDocument]:
    """출처 행에 쓸 실거래 원문 행 — 모든 사례를 한 번에 읽는다(사례마다 조회하지 않는다)."""
    ids = sorted({t.raw_document_id for c in cases for t in c.post if t.raw_document_id is not None})
    out: dict[int, RawDocument] = {}
    for i in range(0, len(ids), _IN_CHUNK):
        for d in session.scalars(select(RawDocument).where(RawDocument.id.in_(ids[i : i + _IN_CHUNK]))):
            out[d.id] = d
    return out


def _write_prov(
    session: Session,
    row: Benchmark,
    case: _Case,
    vals: dict[str, Any],
    tag: str,
    sub: bool,
    by_id: dict[int, RawDocument],
) -> None:
    n, sale = case.notice, case.sale
    label: Label = "추정" if sub else SALE_LABEL
    trade_labels: list[Label] = ["확인됨" if t.source == "openapi" else "재가공" for t in case.trades]
    trade_label: Label = "추정" if sub else weakest_label(*trade_labels)
    sub_reason = "대체: 지역 전체" if sub else None
    win = f"{case.window} 전용 80~85㎡ 해제 제외 {vals['n_trades']}건"
    peak = _peak(case.post)
    median_src = sorted(case.trades, key=lambda t: (t.price_won, t.deal_date))[len(case.trades) // 2]
    low = min(case.trades, key=lambda t: (t.price_won, t.deal_date))
    high = max(case.trades, key=lambda t: (t.price_won, t.deal_date))
    span = json_object_at(n.text, "HOUSE_MANAGE_NO", n.hm)
    notice_ex = n.text[span[0] : span[1]] if span else n.name
    news = case.news
    if (
        news is not None
    ):  # D31-3 분양가 = 언론 기사(판정기 추출), 분양 연도 = 식(추정), 준공 연도 = rtms 건축년도
        built = next((t for t in case.post if t.completed_year == vals["completed_year"]), case.post[0])
        built_doc = by_id.get(built.raw_document_id) if built.raw_document_id is not None else None
        rows = [
            prov_row(
                entity="benchmark", entity_id=row.id, key=tag, field_name="sale_price_84_won", value=sale.won,
                value_text=f"{_fmt_won(sale.won)} (기사 '{news.value_text}')", doc=sale.doc,
                label="추정" if sub else news.label, reason=sub_reason or news.basis, excerpt=news.excerpt,
                observed_on=news.article_date, url=news.article_url,
            ),
            prov_row(
                entity="benchmark", entity_id=row.id, key=tag, field_name="sale_year", value=vals["sale_year"],
                value_text=str(vals["sale_year"]), doc=sale.doc, label="추정",
                reason=sub_reason or news.sale_year_formula, excerpt=news.excerpt, observed_on=news.article_date,
                url=news.article_url,
            ),
        ]  # fmt: skip
        if built_doc is not None:
            rows.append(
                prov_row(
                    entity="benchmark", entity_id=row.id, key=tag, field_name="completed_year",
                    value=vals["completed_year"], value_text=f"건축년도 {vals['completed_year']}", doc=built_doc,
                    label="추정" if sub else ("확인됨" if built.source == "openapi" else "재가공"),
                    reason=sub_reason or "rtms 건축년도(준공 연도)",
                    excerpt=f"{built.apt_name} 건축년도 {built.completed_year} {built.deal_date}",
                    observed_on=built.deal_date,
                )
            )  # fmt: skip
    else:
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
    "substitute",
    "note",
)


def _snapshot_for(session: Session, region_id: int, asof_date: str) -> int | None:
    """호출자가 스냅샷을 주지 않으면: 이 지역·기준일의 가장 새 스냅샷(없으면 None)."""
    return session.scalars(
        select(Snapshot.id)
        .where(Snapshot.region_id == region_id, Snapshot.asof_date == asof_date)
        .order_by(Snapshot.id.desc())
        .limit(1)
    ).first()


def build_benchmarks(
    session: Session,
    region_id: int,
    *,
    asof_date: str,
    snapshot_id: int | None = None,
    news_prices: Sequence[NewsPrice] | None = None,
) -> BenchmarkBuild:
    """지역의 벤치마크 행을 다시 조립한다(멱등). commit 은 호출자.

    행은 스냅샷에 묶인다(계약 .6 ``benchmark.snapshot_id``): 다시 돌리면 **같은 스냅샷**의 자기 행만 갱신·삭제하고,
    다른 스냅샷(발행본이 인용한 행)은 건드리지 않는다. ``snapshot_id`` 를 안 주면 이 지역·기준일의 가장 새 스냅샷.
    스냅샷 없이 만든 옛 자동 행(머리표 있음, snapshot_id NULL — 0006 이전)은 건드리지 않는다(minor 25: 넘겨받으면 0006
    이전 발행 스냅샷이 인용한 벤치마크가 사라진다). snapshot_id NULL 이고 머리표 없는 행은 수동·시드 행이라 건드리지 않는다.

    ``news_prices`` (D31-3) = 언론 기사 분양가(호출자가 판정기로 고른 값). None 이면(판정기·뉴스 키 없음) 이 스냅샷의
    기존 언론 사례 행(머리표 ``[bm:news:``)을 지우지 않고 그대로 둔다.
    """
    region = session.get(Region, region_id)
    if region is None:
        raise LookupError(f"region {region_id} 없음")
    sid = snapshot_id if snapshot_id is not None else _snapshot_for(session, region_id, asof_date)
    res = BenchmarkBuild()
    asof_year = int(asof_date[:4])
    cases = _cases(session, region, asof_date, res)
    cases += _news_cases(session, region, asof_date, news_prices or (), res)
    docs = _trade_docs(session, cases)
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
                tag = (
                    f"{c.tag[:-1]}:{la}]"
                    if c.news is not None
                    else f"{BENCHMARK_TAG}{c.notice.hm}:{c.notice.pb}:{la}]"
                )
                vals = _values(c, asof_year)
                vals.update(living_area=la, sale_price_label="추정", substitute=True)
                vals["note"] = _note(c, vals, tag, la)
                wanted.append((tag, c, vals, la))

    existing: dict[str, Benchmark] = {}
    for b in session.scalars(
        select(Benchmark).where(Benchmark.region_id == region.id).order_by(Benchmark.id)
    ):
        if not (b.note and b.note.startswith(BENCHMARK_TAG)):
            continue
        tag_of = b.note.split("]", 1)[0] + "]"
        if b.snapshot_id == sid:
            existing.setdefault(tag_of, b)
        # 스냅샷 없이 만든 옛 자동 행(snapshot_id NULL, 0006 이전)은 넘겨받지 않는다(minor 25) — 0006 이전 발행 스냅샷이
        # 인용하던 행이라 그대로 두고(``api.benchmarks.benchmarks_for`` 가 조립분이 없는 스냅샷에만 보인다) 새 행을 만든다
    seen: set[str] = set()
    for tag, case, vals, sub in wanted:
        seen.add(tag)
        row = existing.get(tag)
        cols = {k: vals[k] for k in _COLUMNS}
        if row is None:
            row = Benchmark(region_id=region.id, snapshot_id=sid, **cols)
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
        _write_prov(session, row, case, vals, tag, sub is not None, docs)
    for tag, row in existing.items():
        if news_prices is None and tag.startswith(NEWS_TAG):
            continue  # 이번에 언론 분양가를 못 받았다 — 지난 행을 지우지 않는다
        if tag not in seen:
            unchoose_provenance(session, "benchmark", row.id)
            session.delete(row)
            res.removed += 1
    session.flush()
    return res
