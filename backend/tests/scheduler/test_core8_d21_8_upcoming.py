"""D21-8(R4 재시험 FE9 보고) — 트랙 (A) 공고 예정 후보 행(``normalize.upcoming`` 이 만든 모양)의 공고일·가격 = '확인 불가(공고 전)',
단지 이름 출처·라벨(``name_prov``·``name_label`` = 언론 '비공식').

R4 재시험: 공고 예정 후보 2곳(검단 센트레빌 그랑포레·카이브 유보라)은 이름 출처 행만 있고(라벨 '비공식') 공고일 출처 행이 없어 상세
공고일이 '확인 불가(값 없음)', 가격이 '확인 불가(분양가 미공개)'로 보였다(FE9 — 화면은 '공고 전'을 기대). 픽스처 시드(devseed)의
후보는 공고일 출처 행에 사유 '공고 전'이 있어 이 차이가 드러나지 않는다 — 그래서 수집 경로와 같은 모양의 행으로 시험한다.
"""

# ruff: noqa: E501

from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from app.api.facts import FactMaker, ProvIndex
from app.api.views import complex_header, load_bundles, price_range
from app.core.contracts_gen import ProvenanceRow
from app.core.settings import Settings
from app.models import Complex, RawDocument
from app.normalize.provenance import upsert_provenance


def _candidate(s: Session) -> int:
    raw = RawDocument(
        source_kind="news", url="https://openapi.example/news?q=x", fetched_at="2026-10-08T05:00:00+09:00",
        http_status=200, sha256="d" * 64, path="news/2026-10-08/" + "d" * 64 + ".json", region_id=1,
    )  # fmt: skip
    s.add(raw)
    s.flush()
    cx = Complex(
        region_id=1, applyhome_id=None, name="검단 센트레빌 그랑포레", former_names=[], apply_dates=[], contract_dates=[],
        inclusion_class="private_sale_apt", inclusion_decision="auto", track="A",
    )  # fmt: skip
    s.add(cx)
    s.flush()
    upsert_provenance(
        s,
        [
            ProvenanceRow(
                entity="complex", entity_id=cx.id, entity_key=f"upcoming:{cx.id}", field="name", value_text=cx.name,
                value_norm=cx.name, raw_document_id=raw.id, url="https://news.example/a", checked_at="2026-10-08",
                observed_on=None, label="비공식", reason="언론(공고 예정, 청약홈 미등록)", source_rank=3, chosen=True,
                conflict_group=None, excerpt="이달 검단구 오류동 843세대 분양 예정", excerpt_start=None, excerpt_end=None,
            )
        ],
    )  # fmt: skip
    s.commit()
    return cx.id


def test_upcoming_candidate_header_and_price_say_pre_notice(
    factory: sessionmaker[Session], seeded: int, test_settings: Settings
) -> None:
    with factory() as s:
        cid = _candidate(s)
        cx = s.get(Complex, cid)
        assert cx is not None
        b = load_bundles(s, [cx], seeded)[cid]
        fm = FactMaker(test_settings, ProvIndex().load(s, "complex", [cid]))
        head = complex_header(fm, b, {})
        assert (head["notice_date"]["label"], head["notice_date"]["reason"]) == ("확인 불가", "공고 전")
        assert (head["name_prov"], head["name_label"]) == (
            f"fp_{fm.prov.get('complex', cid, 'name').id}",
            "비공식",
        )  # type: ignore[union-attr]
        for notice in (head["notice_date"], None):
            price = price_range(fm, b, notice)
            for key in ("price_low", "price_high", "price_mid"):
                assert (price[key]["label"], price[key]["reason"]) == ("확인 불가", "공고 전"), (
                    key,
                    price[key],
                )
