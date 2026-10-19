"""수집 뒤 데이터 조립 (R3 F1a: C1·M5·M6·M7) — ``collect.collect`` 가 수집 단계를 다 돈 다음 부른다.

| 수집 단계(이번 잡에서 돈 것) | 조립 | 결과 |
| --- | --- | --- |
| applyhome | ``normalize.remaining.sync_remaining_events`` | remaining_event(+ 새 공고 critical change_event) |
| applyhome · notice_pdf | ``normalize.checklist.sync_checklist`` | checklist_item |
| rtms (= collect.weekly) | 청약홈 과거 공고(``fetch_history``, 기본 10년) + rtms 과거 월(``backfill``, 36개월) 수집 →
  ``normalize.benchmark.build_benchmarks`` | benchmark + 출처(+ 바뀌면 notice change_event → 주간 rejudge) |
| rtms | 문자열로 못 이은 공고마다 같은 동·준공 ±1년 실거래 후보 → 판정기 classify(같은 단지, auto 만) →
  ``build_benchmarks(links=…)`` | 이름이 바뀐 단지 매칭(D31-6) — stats ``benchmark_links`` |
| rtms (+ news 수집기) | 2020년 이전 분양 단지(준공 10년 안, 공고와 안 이어짐)마다 뉴스 '<이름> 분양가' 1회 검색(받은 원문 재사용) →
  판정기 P2 extract(그 단지 84㎡ 분양가) → ``build_benchmarks(news_prices=…)`` | 언론 기사 분양가 사례(D31-3, 라벨 비공식·추정) — stats ``benchmark_news`` |
| news | 판정기 P1 screen(호재 관련성, ``judge.pipeline.p1_screen_catalyst``) 통과 항목만 → ``normalize.catalyst.catalysts_from_news`` | catalyst 후보(단계·종류는 판정기 P4, D10-6) — 거른 수는 stats ``rejected`` |
| news | 판정기 screen(공고 예정 신호)·extract(단지 이름)·classify(지역·민간분양)·compare(같은 단지) → ``normalize.upcoming.upcoming_from_news`` | 트랙 (A) 공고 예정 단지 후보(D20-2) — stats ``upcoming`` |

과거 공고·과거 월 수집은 ``ctx.collectors`` 의 ``applyhome``·``rtms`` 수집기에 그 메서드가 있을 때만 한다(가짜 수집기·
키 없음이면 건너뛰고, 이미 받아 둔 원문으로 조립한다). 조립 단계마다 예외를 ``errors['assemble.<단계>']`` 에 남기고
(비밀값·개인정보 가림) 다른 단계는 계속한다 — collect 의 수집 단계와 같은 규칙.
"""

# ruff: noqa: E501  (한국어 docstring·로그 필드)

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy.orm import Session

from app.collectors.news.collector import NewsItem
from app.core.contracts_gen import RawDocument as RawDTO
from app.core.contracts_gen import Region as RegionDTO
from app.core.contracts_gen import Snapshot as SnapshotDTO
from app.core.logging import get_logger
from app.core.protocols import JudgeUnavailable
from app.core.redact import redact_text
from app.core.settings import get_settings
from app.judge import pipeline as jp
from app.models import ChangeEvent
from app.normalize.benchmark import build_benchmarks
from app.normalize.benchmark_news import NewsPrice
from app.normalize.catalyst import catalysts_from_news
from app.normalize.checklist import sync_checklist
from app.normalize.remaining import sync_remaining_events

if TYPE_CHECKING:
    from app.scheduler.context import SchedulerContext

__all__ = [
    "BENCHMARK_HISTORY_YEARS",
    "BENCHMARK_NEWS_MAX",
    "RTMS_BACKFILL_MONTHS",
    "AssembleResult",
    "assemble",
    "news_key",
    "safe_error",
]

log = get_logger("app.scheduler.assemble")

BENCHMARK_HISTORY_YEARS: Final = 10  # D9-2 기본 N년 (청약홈 API 자료는 2020년부터 — 2026-10-09 확인)
RTMS_BACKFILL_MONTHS: Final = 36  # 입주 후 실거래(고점 포함)를 볼 과거 월 수
BENCHMARK_NEWS_MAX: Final = 300  # D31-3 한 번에 새로 검색할 단지 수(나머지는 다음 주간 수집)


@dataclass
class AssembleResult:
    stats: dict[str, Any] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    events: list[ChangeEvent] = field(default_factory=list)  # 저장됨(id 있음)


def news_key(url: str | None, title: str) -> str:
    """뉴스 호재 후보의 판정 purpose 키(출처 URL·제목 해시) — screen(수집)·classify(파이프라인)가 같은 키를 쓴다.
    행 id 가 아니라서 같은 기사가 다시 들어와도 같은 purpose = 캐시(판정 재호출 없음)."""
    import hashlib

    return "n" + hashlib.sha256(f"{url or ''}|{title}".encode()).hexdigest()[:16]


def safe_error(exc: BaseException) -> str:
    """잡 stats·errors 로 나가는 예외 문구 — 비밀값·개인정보를 가리고 자른다."""
    try:
        secrets = get_settings().secret_values()
    except Exception:  # 설정을 못 읽어도 문구는 남긴다(형태 패턴은 그대로 가린다)
        secrets = []
    return redact_text(f"{type(exc).__name__}: {str(exc)[:200]}", secrets)


def assemble(
    ctx: SchedulerContext,
    region: RegionDTO,
    snapshot: SnapshotDTO,
    *,
    steps: Collection[str],
    docs: Mapping[str, Sequence[RawDTO]],
    detected_at: str,
    links: Mapping[str, int] | None = None,
    first_load: bool = False,
) -> AssembleResult:
    res = AssembleResult()

    def run(name: str, fn: Callable[[], None]) -> None:
        try:
            fn()
        except Exception as exc:  # 조립 버그·환경 오류: 다른 단계는 계속, 잡은 failed
            res.errors[f"assemble.{name}"] = safe_error(exc)
            log.exception("worker.assemble.error", extra={"part": name, "region_id": region.id})

    def remaining() -> None:
        with ctx.session_factory() as s:
            out = sync_remaining_events(
                s, region.id, snapshot_id=snapshot.id, detected_at=detected_at, links=links,
                first_load=first_load,
            )  # fmt: skip
            s.commit()
            res.stats["remaining"] = out.stats()
            res.events.extend(out.events)

    def checklist() -> None:
        with ctx.session_factory() as s:
            out = sync_checklist(s, region.id, asof_date=snapshot.asof_date)
            s.commit()
            res.stats["checklist"] = out.stats()

    def history() -> None:
        factory = ctx.collectors.get("applyhome")
        collector = factory(ctx) if factory is not None else None
        fetch = getattr(collector, "fetch_history", None)
        if not callable(fetch):
            res.stats["benchmark_history"] = {"skipped": "수집기에 과거 공고 조회 없음"}
            return
        got = fetch(region, snapshot, years=BENCHMARK_HISTORY_YEARS)
        res.stats["benchmark_history"] = {
            "documents": len(got),
            "failed": sum(1 for d in got if d.http_status != 200),
            **dict(getattr(collector, "history_stats", {}) or {}),
        }

    def backfill() -> None:
        factory = ctx.collectors.get("rtms")
        collector = factory(ctx) if factory is not None else None
        fill = getattr(collector, "backfill", None)
        if not callable(fill) or getattr(collector, "enabled", True) is False:
            res.stats["rtms_backfill"] = {"skipped": "수집기에 과거 월 채우기 없음(또는 비활성)"}
            return
        got = fill(region, snapshot, months=RTMS_BACKFILL_MONTHS)
        load = getattr(collector, "load_stats", None)
        res.stats["rtms_backfill"] = {
            "documents": len(got),
            "failed": sum(1 for d in got if d.http_status != 200),
            "inserted": int(getattr(load, "inserted", 0) or 0),
        }
        legal = getattr(load, "legal_dong_stats", None)
        if callable(legal):  # D18-3 법정동 매칭률
            res.stats["rtms_backfill"]["legal_dong"] = legal()

    judge_links: dict[
        str, dict[str, tuple[str, str]]
    ] = {}  # 'map' 이 없으면 판정기 매칭을 못 함 → 지난 행 유지

    def benchmark_links() -> None:
        """D31-6 이름으로 못 이은 공고 → 같은 동 실거래 후보 중 같은 단지(판정기 classify, auto 만)."""
        from app.judge.payloads import BENCHMARK_LINK_NONE
        from app.normalize.benchmark_link import link_requests

        with ctx.session_factory() as s:
            reqs = link_requests(s, region.id, snapshot.asof_date)
        out: dict[str, tuple[str, str]] = {}
        skipped: dict[str, int] = {}
        for rq in reqs:
            try:
                o = jp.p4_classify_benchmark_link(
                    ctx.adapter(), notice_key=rq.key, text=rq.text,
                    candidates=[(c.cid, c.text) for c in rq.candidates], snapshot_id=snapshot.id,
                )  # fmt: skip
            except JudgeUnavailable:
                res.stats["benchmark_links"] = {"skipped": "판정기 연결 실패 — 판정기로 이은 지난 행 유지"}
                return
            chosen = next((c for c in rq.candidates if o.resolved and c.cid == o.label), None)
            if chosen is not None and o.label != BENCHMARK_LINK_NONE:
                out[rq.key] = (chosen.name, chosen.dong)
            else:
                why = "후보 중 없음" if o.resolved else "판정 미해결"
                skipped[why] = skipped.get(why, 0) + 1
        judge_links["map"] = out
        res.stats["benchmark_links"] = {"requests": len(reqs), "linked": len(out), "skipped": skipped}

    news_prices: dict[str, list[NewsPrice]] = {}  # 'prices' 가 없으면 언론 분양가를 못 받음 → 지난 행 유지

    def benchmark_news() -> None:
        """D31-3 2020년 이전 분양 단지 분양가 — 뉴스 검색(단지마다 1회, 받은 원문 재사용) → 판정기 P2 extract."""
        from app.collectors.news.collector import parse_news_json
        from app.normalize.benchmark import latest_by_urls, read_raw_row
        from app.normalize.benchmark_news import news_document, news_price, news_query, news_targets

        factory = ctx.collectors.get("news")
        collector = factory(ctx) if factory is not None else None
        search, url_of = getattr(collector, "search", None), getattr(collector, "search_url", None)
        if not callable(search) or not callable(url_of) or getattr(collector, "enabled", True) is False:
            res.stats["benchmark_news"] = {"skipped": "뉴스 수집기에 검색 없음(또는 키 없음)"}
            return
        with ctx.session_factory() as s:
            targets = news_targets(s, region.id, snapshot.asof_date, judge_links.get("map"))
            urls = {t.key: str(url_of(news_query(t.name, t.place))) for t in targets}
            have = latest_by_urls(s, urls.values())
        missing = [t for t in targets if urls[t.key] not in have][:BENCHMARK_NEWS_MAX]
        if missing:
            search(region, [news_query(t.name, t.place) for t in missing])
        skipped: dict[str, int] = {}
        prices: list[NewsPrice] = []
        with ctx.session_factory() as s:
            docs = latest_by_urls(s, urls.values())
            for t in targets:
                doc = docs.get(urls[t.key])
                text = read_raw_row(doc) if doc is not None else None
                document, spans = news_document(t, parse_news_json(text.encode()) if text else [])
                if doc is None or not spans:
                    why = "기사 원문 없음" if doc is None else "기사 없음"
                    skipped[why] = skipped.get(why, 0) + 1
                    continue
                s.commit()  # 어댑터는 자기 세션으로 judgment_log 를 쓴다 — 읽기 잠금(SQLite)을 먼저 푼다
                try:
                    fields = jp.p2_extract_benchmark_price(
                        ctx.adapter(),
                        target_key=t.key,
                        name=t.name,
                        document=document,
                        snapshot_id=snapshot.id,
                        place=t.place,
                    )
                except JudgeUnavailable:
                    res.stats["benchmark_news"] = {"skipped": "판정기 연결 실패 — 지난 언론 분양가 행 유지"}
                    return
                price, why = news_price(t, document, spans, fields, raw_document_id=doc.id)
                if price is None:
                    skipped[why] = skipped.get(why, 0) + 1
                else:
                    prices.append(price)
        news_prices["prices"] = prices
        res.stats["benchmark_news"] = {
            "targets": len(targets), "searched": len(missing), "prices": len(prices), "skipped": skipped,
        }  # fmt: skip

    def benchmark() -> None:
        with ctx.session_factory() as s:
            # 조립한 스냅샷을 남긴다(계약 .6 benchmark.snapshot_id — 발행 스냅샷이 인용한 행 보존, G1)
            out = build_benchmarks(
                s, region.id, asof_date=snapshot.asof_date, snapshot_id=snapshot.id,
                news_prices=news_prices.get("prices"), links=judge_links.get("map"),
            )  # fmt: skip
            if out.changed:
                res.events.append(_event(s, snapshot.id, out.inserted, out.updated, out.removed, detected_at))
            s.commit()
            res.stats["benchmark"] = out.stats()

    def catalyst() -> None:
        screened: dict[str, str] = {}
        session: Session

        def accept(item: NewsItem) -> bool:
            """D10-6: 뉴스 항목 → P1 screen(호재 관련성) usable 만 후보. 판정기가 죽어 있으면 이번에는 만들지 않는다
            (후보가 아니므로 다음 수집에 다시 검사 — 같은 입력이면 캐시)."""
            # 어댑터는 자기 세션으로 judgment_log 를 쓴다 — 후보 세션의 쓰기 잠금(SQLite)을 먼저 푼다(pipeline 과 같은 규칙)
            session.commit()
            try:
                out = jp.p1_screen_catalyst(
                    ctx.adapter(), catalyst_key=news_key(item.url, item.title), title=item.title,
                    excerpt=item.excerpt, url=item.url, snapshot_id=snapshot.id,
                )  # fmt: skip
            except JudgeUnavailable:
                screened["unavailable"] = "판정기 연결 실패 — 이번 수집은 후보를 만들지 않음"
                return False
            return out.usable

        with ctx.session_factory() as session:
            out = catalysts_from_news(session, region.id, docs.get("news", []), accept=accept)
            session.commit()
            res.stats["catalyst"] = {**out.stats(), **({"screen": screened} if screened else {})}

    if "applyhome" in steps:
        run("remaining", remaining)
    if "applyhome" in steps or "notice_pdf" in steps:
        run("checklist", checklist)
    if "rtms" in steps:
        run("benchmark_history", history)
        run("rtms_backfill", backfill)
        run("benchmark_links", benchmark_links)
        run("benchmark_news", benchmark_news)
        run("benchmark", benchmark)

    def upcoming() -> None:
        from app.normalize.upcoming import upcoming_from_news

        judge = _UpcomingJudge(ctx, region, snapshot.id)
        with ctx.session_factory() as s:
            out = upcoming_from_news(
                s, region.id, docs.get("news", []), judge=judge, key_of=lambda it: news_key(it.url, it.title),
                snapshot_id=snapshot.id, detected_at=detected_at,
            )  # fmt: skip
            s.commit()
            res.stats["upcoming"] = {**out.stats(), **({"screen": judge.errors} if judge.errors else {})}
            res.events.extend(out.events)

    if "news" in steps:
        run("catalyst", catalyst)
        run("upcoming", upcoming)
    return res


class _UpcomingJudge:
    """D20-2 ``normalize.upcoming.UpcomingJudge`` 구현 — 판정기 단계 함수(``judge.pipeline``)만 부른다. 판정기가 죽어 있으면
    이번 수집은 후보를 만들지 않는다(다음 수집에 다시 — 같은 입력이면 캐시)."""

    def __init__(self, ctx: SchedulerContext, region: RegionDTO, snapshot_id: int) -> None:
        self.ctx, self.snapshot_id = ctx, snapshot_id
        names = [s.full_name for s in region.selections]
        self.region_text = f"분석 지역: {region.name} ({', '.join(names)})"
        self.errors: dict[str, str] = {}

    def screen(self, item: NewsItem, key: str) -> bool:
        try:
            return jp.p1_screen_upcoming(
                self.ctx.adapter(), news_key=key, title=item.title, excerpt=item.excerpt, url=item.url,
                snapshot_id=self.snapshot_id,
            ).usable  # fmt: skip
        except JudgeUnavailable:
            self.errors["unavailable"] = "판정기 연결 실패 — 이번 수집은 공고 예정 후보를 만들지 않음"
            return False

    def names(self, item: NewsItem, key: str) -> list[str]:
        doc = f"제목: {item.title}\n발췌: {item.excerpt}"
        try:
            return jp.p2_extract_upcoming(
                self.ctx.adapter(), news_key=key, document=doc, snapshot_id=self.snapshot_id
            )
        except JudgeUnavailable:
            self.errors["unavailable"] = "판정기 연결 실패 — 이번 수집은 공고 예정 후보를 만들지 않음"
            return []

    def classify(self, item: NewsItem, key: str, names: list[str]) -> dict[str, Any]:
        from app.normalize.upcoming import ClassifiedName

        items = [
            (f"name{i}", f"{self.region_text}\n단지: {n}\n기사: {item.title} — {item.excerpt}")
            for i, n in enumerate(names)
        ]
        try:
            outs = jp.p4_classify_upcoming(
                self.ctx.adapter(), news_key=key, items=items, snapshot_id=self.snapshot_id
            )
        except JudgeUnavailable:
            self.errors["unavailable"] = "판정기 연결 실패 — 이번 수집은 공고 예정 후보를 만들지 않음"
            return {}
        return {
            n: ClassifiedName(o.label, o.prob, o.envelope.judgment_seq, o.resolved)
            for n, o in ((n, outs[f"name{i}"]) for i, n in enumerate(names))
        }

    def same(self, a: str, a_text: str, b: str, b_text: str) -> bool:
        import hashlib

        pair = "|".join(sorted((a, b)))
        key = hashlib.sha256(pair.encode()).hexdigest()[:16]
        try:
            return jp.p5_same_complex(
                self.ctx.adapter(), f"단지: {a}\n{a_text}", f"단지: {b}\n{b_text}", pair_key=key,
                snapshot_id=self.snapshot_id,
            )  # fmt: skip
        except JudgeUnavailable:
            return False


def _event(s: Session, snapshot_id: int, ins: int, upd: int, rem: int, detected_at: str) -> ChangeEvent:
    ev = ChangeEvent(
        snapshot_id=snapshot_id,
        entity="benchmark",
        entity_id=None,
        field="rows",
        old_text=None,
        new_text=f"추가 {ins}건, 갱신 {upd}건, 삭제 {rem}건",
        detected_at=detected_at,
        severity="notice",
        triggers_rejudge=False,
        complex_id=None,
    )
    s.add(ev)
    s.flush()
    return ev
