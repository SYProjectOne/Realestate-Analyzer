"""벤치마크 분양가 — 2020년 이전 분양 단지의 언론 기사 분양가 (D31-3, RA §3 benchmark '언론 역산은 추정 라벨').

청약홈 공식 API 과거 공고는 2020-02부터만 있고(웹 목록은 최근 5년) 그 전에 분양한 단지는 분양가 원천이 없어 벤치마크에서
빠졌다. 이 모듈은 문자열 처리만 한다 — 기사에서 '그 단지의 84㎡ 분양가'를 고르는 것은 판정기(P2 extract,
``judge.pipeline.p2_extract_benchmark_price``)다(AGENTS 규칙 3).

1. ``news_targets`` — 생활권 안 실거래 단지 중 준공(rtms 건축년도)이 기준연도 − ``NEWS_YEARS`` 이후이고, 최근 12개월 일반
   거래가 있고, 어떤 공고와도 이어지지 않은 단지(``BenchmarkBuild.matched_groups`` 밖, 같은 동 다른 표기 포함).
2. ``news_query`` — 검색어 '<실거래 이름(괄호 뺀)> 분양가'. 수집기는 관련도순으로 한 번 받고, 받은 원문을 다시 쓴다.
3. ``news_document`` — 받은 기사 목록 → 판정기 입력(머리 줄 + 번호 붙인 기사 줄).
4. ``news_price`` — 판정기가 auto 로 고른 값 → 원 단위 + 그 값이 든 기사 줄(출처). 범위 밖 값은 버린다(단위 검사).

라벨: 기사에 난 전용 84㎡ 분양가 = 비공식(언론). 3.3㎡당 평균 분양가만 있으면 × ``PYEONG_PER_84`` = 추정(언론 역산).
분양 연도 = min(기사 연도, 준공 연도 − 2) — 분양 뒤 입주까지 2년 넘게 걸린다는 가정(라벨 추정, 식은 note).
공공분양이라고 밝힌 단지(판정기 auto)는 대상이 아니다(벤치마크 = 민영, D9-2).
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import TYPE_CHECKING, Final

from sqlalchemy.orm import Session

from app.analysis.types import Label
from app.models import Region
from app.normalize.living_area import living_area_of

if TYPE_CHECKING:
    from app.collectors.news.collector import NewsItem

__all__ = [
    "NEWS_TAG",
    "NEWS_YEARS",
    "PYEONG_PER_84",
    "NewsPrice",
    "NewsTarget",
    "money_won",
    "news_document",
    "news_price",
    "news_query",
    "news_targets",
]

NEWS_TAG: Final = "[bm:news:"
NEWS_YEARS: Final = 10  # D9-2 과거 N년(청약홈 과거 공고 창과 같은 수)
PYEONG_PER_84: Final = 34  # 전용 84㎡ 공급면적 약 112㎡ ÷ 3.3㎡ (가정 — note 에 식)
MIN_SALE_WON: Final = 100_000_000
MAX_SALE_WON: Final = 5_000_000_000
MIN_PER_PYEONG_WON: Final = 3_000_000
MAX_PER_PYEONG_WON: Final = 100_000_000
_PAREN: Final = re.compile(r"\([^)]*\)")
PRICE_PATTERNS: Final = (
    r"\d+\s?억(?:\s?\d+\s?천)?(?:\s?\d[\d,]*)?\s?만?\s?원",  # price_84
    r"\d[\d,]{2,5}\s?만\s?원",  # price_per_3_3
    "공공분양",  # public_sale
)
"""판정기 extract 필드 정규식(``judge.payloads.benchmark_price_extract_fields`` 와 같은 값 — 테스트가 맞춘다)."""
_CANDIDATE: Final = re.compile("|".join(f"(?:{p})" for p in PRICE_PATTERNS))
_MONEY: Final = re.compile(r"(?:(\d+)억)?(?:(\d+)천)?(?:(\d+)백)?(\d+)?(만)?원?")


@dataclass(frozen=True)
class NewsTarget:
    key: str  # 'nt' + sha256(정규화 이름|법정동)[:12] — 판정 purpose·행 머리표
    name: str  # 대표 실거래 이름(원문, 가장 많이 나온 표기)
    norm: str  # 정규화 이름(실거래 묶음 키)
    dong: str
    living_area: str
    completed_year: int


@dataclass(frozen=True)
class NewsPrice:
    target: NewsTarget
    won: int
    label: Label  # 비공식(기사 84㎡ 값) | 추정(3.3㎡당 × 34)
    basis: str  # note·출처 사유
    value_text: str  # 판정기가 고른 원문 문자열
    excerpt: str  # 그 값이 든 기사 줄
    article_url: str
    article_date: str | None  # YYYY-MM-DD
    sale_year: int
    sale_year_formula: str
    raw_document_id: int


def target_key(norm: str, dong: str) -> str:
    return "nt" + hashlib.sha256(f"{norm}|{dong}".encode()).hexdigest()[:12]


def news_query(name: str) -> str:
    """검색어 — 괄호(영문 표기·블록) 뺀 실거래 이름 + ' 분양가'."""
    return f"{' '.join(_PAREN.sub(' ', name).split())} 분양가"


def news_targets(session: Session, region_id: int, asof_date: str) -> list[NewsTarget]:
    """뉴스 분양가를 찾을 실거래 단지(생활권 안, 준공 10년 안, 최근 12개월 일반 거래, 공고와 안 이어짐)."""
    from app.normalize import benchmark as bm

    region = session.get(Region, region_id)
    if region is None:
        raise LookupError(f"region {region_id} 없음")
    res = bm.BenchmarkBuild()
    bm._cases(session, region, asof_date, res)  # 공고와 이어진 묶음(성공·실패 모두) = res.matched_groups
    used = res.matched_groups
    asof_ym = asof_date[:7]
    win_start = bm.add_months_ym(asof_ym, -(bm.TRADE_WINDOW_MONTHS - 1))
    min_year = int(asof_date[:4]) - NEWS_YEARS
    groups = bm._trade_groups(session, region_id)
    out: list[NewsTarget] = []
    for g in groups:
        if (g.name, g.dong) in used or any(
            d == g.dong and _alias(n, g.name) for n, d in used
        ):  # 같은 동 다른 표기도 공고 쪽
            continue
        general = [t for t in g.trades if not t.is_presale and t.deal_date[:10] <= asof_date]
        if not any(t.deal_date[:7] >= win_start for t in general):
            continue
        years = Counter(t.completed_year for t in general if t.completed_year)
        codes = Counter(t.legal_dong_code for t in general if t.legal_dong_code)
        if not years or not codes:
            continue
        year = years.most_common(1)[0][0]
        if year < min_year or year > int(asof_date[:4]):
            continue
        la = living_area_of(codes.most_common(1)[0][0], region.living_areas or [])
        if la is None:
            continue
        name = Counter(t.apt_name for t in general).most_common(1)[0][0]
        out.append(NewsTarget(target_key(g.name, g.dong), name, g.name, g.dong, la, year))
    return sorted(out, key=lambda t: (t.living_area, t.name))


def _alias(a: str, b: str) -> bool:
    from app.normalize.benchmark import ALIAS_MIN_CHARS

    short, long_ = sorted((a, b), key=len)
    return len(short) >= ALIAS_MIN_CHARS and long_.endswith(short)


def _day(published_at: str | None) -> str | None:
    if not published_at:
        return None
    try:
        return parsedate_to_datetime(published_at).date().isoformat()
    except (TypeError, ValueError):
        return published_at[:10] if re.match(r"\d{4}-\d{2}-\d{2}", published_at) else None


def news_document(target: NewsTarget, items: list[NewsItem]) -> tuple[str, list[tuple[int, int, NewsItem]]]:
    """판정기 입력 문서와 기사 줄 위치 [(시작, 끝, 기사)]. 남는 기사가 없으면 ('', []).

    추출 후보(필드 정규식에 맞는 문자열)가 없는 기사, 앞 기사에 이미 나온 후보(공백·쉼표 뺀 문자열)만 되풀이하는 기사는
    넣지 않는다 — 같은 값이 여러 번 나오면 판정기 확률이 나뉘어 auto 가 안 된다(문자열 중복 제거 — 판단 아님)."""
    seen: set[str] = set()
    kept: list[tuple[int, NewsItem]] = []
    for i, it in enumerate(items, start=1):
        found = {
            m.group(0).replace(" ", "").replace(",", "")
            for m in _CANDIDATE.finditer(f"{it.title} {it.excerpt}")
        }
        if found - seen:
            kept.append((i, it))
            seen |= found
    if not kept:
        return "", []
    lines = [f"단지: {target.name} (법정동 {target.dong}, 준공 {target.completed_year}년)"]
    pos = len(lines[0]) + 1
    spans: list[tuple[int, int, NewsItem]] = []
    for i, it in kept:
        line = f"[{i}] {_day(it.published_at) or '날짜 없음'} {it.title} — {it.excerpt}"
        spans.append((pos, pos + len(line), it))
        lines.append(line)
        pos += len(line) + 1
    return "\n".join(lines), spans


def money_won(text: str) -> int | None:
    """'4억3000만원'·'4억 800만 원'·'3억 9천만원'·'1,247만원'·'4억원' → 원. 못 읽으면 None (파싱 — 판단 아님)."""
    m = _MONEY.fullmatch(text.replace(" ", "").replace(",", ""))
    if m is None or not any(m.group(i) for i in (1, 2, 3, 4)):
        return None
    eok, cheon, baek, digits, man = m.groups()
    small = int(cheon or 0) * 1000 + int(baek or 0) * 100 + int(digits or 0)
    return int(eok or 0) * 100_000_000 + small * (10_000 if man else 1) or None


def news_price(
    target: NewsTarget,
    document: str,
    spans: list[tuple[int, int, NewsItem]],
    fields: dict[str, str],
    *,
    raw_document_id: int,
) -> tuple[NewsPrice | None, str]:
    """판정기 auto 값(필드 → 원문 문자열) → (분양가, 사유). 값이 없거나 범위 밖이면 (None, 사유)."""
    if fields.get("public_sale"):
        return None, "공공분양(기사 표현 — 판정기)"
    picked: tuple[str, int, Label, str] | None = None
    raw84 = fields.get("price_84")
    won84 = money_won(raw84) if raw84 else None
    if raw84 and won84 is not None and MIN_SALE_WON <= won84 <= MAX_SALE_WON:
        picked = (raw84, won84, "비공식", "기사에 난 전용 84㎡ 분양가(범위면 높은 값)")
    else:
        raw_pp = fields.get("price_per_3_3")
        pp = money_won(raw_pp) if raw_pp else None
        if raw_pp and pp is not None and MIN_PER_PYEONG_WON <= pp <= MAX_PER_PYEONG_WON:
            won = round(pp * PYEONG_PER_84 / 10_000) * 10_000
            picked = (
                raw_pp,
                won,
                "추정",
                f"언론 역산: 3.3㎡당 평균 분양가 {raw_pp} × {PYEONG_PER_84}(전용 84㎡ 공급면적 약 112㎡ ÷ 3.3㎡)",
            )
    if picked is None:
        return None, "기사에서 분양가를 찾지 못함" if not (
            raw84 or fields.get("price_per_3_3")
        ) else "분양가 단위 확인 불가"
    value_text, won, label, basis = picked
    at = document.find(value_text, len(document.split("\n", 1)[0]))
    hit = next((s for s in spans if s[0] <= at < s[1]), None) if at >= 0 else None
    if hit is None:
        return None, "분양가가 든 기사 줄을 찾지 못함"
    start, end, item = hit
    day = _day(item.published_at)
    pub_year = int(day[:4]) if day else target.completed_year
    sale_year = min(pub_year, target.completed_year - 2)
    formula = f"분양 연도 = min(기사 연도 {pub_year}, 준공 {target.completed_year} − 2) = {sale_year}"
    return (
        NewsPrice(
            target=target,
            won=won,
            label=label,
            basis=basis,
            value_text=value_text,
            excerpt=document[start:end][:500],
            article_url=item.url,
            article_date=day,
            sale_year=sale_year,
            sale_year_formula=formula,
            raw_document_id=raw_document_id,
        ),
        "ok",
    )
