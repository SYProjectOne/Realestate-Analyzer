"""R3c CORE — 정규화 쪽 D11-6 할인과 minor 19·23·24 (계약 2026-10-09.8).

- D11-6: 공고문에 할인 금액이 명시된 줄만 후보(안내 문장·'할인 없음'은 아님) → payment_terms.discount_by_type +
  출처 행 → §6-1 구매가에서 라벨 확인됨일 때만 뺀다. 출처 전수 검사 대상.
- minor 19: normalize_site_url 이 사설·메타데이터·정수 IP·``\\@`` 를 통과시키지 않는다.
- minor 23: 판정기 extract 요청은 발췌 합본이 상한을 넘으면 나눠 보낸다(뒤 필드 발췌가 잘리지 않는다).
- minor 24: 뉴스 후보 조건 위반(CatalystInputError)은 행 없이 넘어가지 않고 stats 에 남는다.
"""

# ruff: noqa: E501

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.price_view import current_price
from app.core.contracts_gen import FieldCandidate
from app.core.contracts_gen import RawDocument as RawDocumentDTO
from app.models import Complex, FieldProvenance, PaymentTerms, Region
from app.normalize._text import normalize_site_url
from app.normalize.extract_request import build_extract_requests
from app.normalize.fields import discount_field
from app.normalize.notice_parser import _DISCOUNT_RE
from app.normalize.provenance import missing_provenance
from app.normalize.store import store_raw_document

from ._support import AddRaw

APT = "https://www.applyhome.co.kr/ai/aia/selectAPTLttotPblancDetail.do?houseManageNo={key}&pblancNo={key}&n={n}"


class _Terms:
    def __init__(self, key: str, values: dict[str, Any]) -> None:
        self.key, self.values = key, values

    def parse(self, raw: RawDocumentDTO) -> list[FieldCandidate]:
        tk = f"{self.key}:{self.key}"
        out = [
            FieldCandidate(
                entity="payment_terms", entity_id=None, entity_key=tk, field=f, value_text=str(v), value=v,  # type: ignore[arg-type]
                source_rank=1, source_kind="notice_pdf", primary=True, label="확인됨", excerpt=f"{f} {v}",
                excerpt_start=0, excerpt_end=1, raw_document_id=raw.id, url=raw.url, checked_at="2026-10-09",
                observed_on="2026-09-01",
            )  # fmt: skip
            for f, v in self.values.items()
        ]
        out.append(
            FieldCandidate(
                entity="complex", entity_id=None, entity_key=self.key, field="name", value_text="할인 단지", value="할인 단지",
                source_rank=1, source_kind="notice_pdf", primary=True, label="확인됨", excerpt="할인 단지",
                excerpt_start=0, excerpt_end=1, raw_document_id=raw.id, url=raw.url, checked_at="2026-10-09",
            )
        )  # fmt: skip
        return out


def test_d11_6_discount_regex_only_explicit_amounts() -> None:
    m = _DISCOUNT_RE.search("84A 분양가 할인 10,000,000원")
    assert m is not None and m.group(1) == "10,000,000"
    assert _DISCOUNT_RE.search("할인금액(84㎡): 12,500,000원") is not None
    assert _DISCOUNT_RE.search("84㎡ 1,245,000,000원(무순위 동일가, 발코니 포함, 할인 없음)") is None
    assert _DISCOUNT_RE.search("선납할인은 적용 되지 않습니다") is None


def test_d11_6_discount_is_stored_with_provenance_and_subtracted_only_when_confirmed(
    db_session: Session, add_raw: AddRaw, region: Region
) -> None:
    raw = add_raw("할인 공고", source_kind="notice_pdf", url=APT.format(key="2026990101", n=1), region_id=region.id)
    values = {
        "effective_from": "2026-09-01", "notice_kind": "본청약",
        "price_by_type.84A.max_price_won": 600_000_000, "price_by_type.84A.floor_sample_price_won": 580_000_000,
        discount_field("84A"): 10_000_000,
    }  # fmt: skip
    store_raw_document(db_session, raw, parser=_Terms("2026990101", values))
    cx = db_session.scalars(select(Complex).where(Complex.applyhome_id == "2026990101")).one()
    pt = db_session.scalars(select(PaymentTerms).where(PaymentTerms.complex_id == cx.id)).one()
    assert pt.discount_by_type == {"84A": 10_000_000}
    fp = db_session.scalars(
        select(FieldProvenance).where(FieldProvenance.entity_id == pt.id, FieldProvenance.field == "discount_by_type.84A")
    ).one()
    assert fp.chosen and fp.label == "확인됨" and fp.value_norm == "10000000"
    assert not [m for m in missing_provenance(db_session, ("payment_terms",)) if m.entity_id == pt.id]

    class T:  # 기준 타입 1개(84A)
        id, type_code, area_m2 = 1, "84A", 84.9
        max_price_won, floor_sample_price_won, balcony_won, options_required_won = 610_000_000, None, None, None

    view = current_price([T()], [pt])  # type: ignore[list-item]
    assert view.discount_applied and view.high_won == 590_000_000 and view.low_won == 570_000_000
    assert "할인" in view.composition and view.discount_ref is not None
    est = current_price([T()], [pt], discount_label=lambda r: "추정")  # type: ignore[list-item]
    assert not est.discount_applied and est.high_won == 600_000_000, "확인됨이 아니면 빼지 않는다(D11-6)"
    pt.discount_by_type = {"84A": 10_000_000, "59A": None}
    db_session.flush()
    gone = current_price([T()], [pt])  # type: ignore[list-item]
    assert gone.high_won == 590_000_000


def test_minor19_site_url_rejects_internal_targets() -> None:
    for bad in (
        "http://10.0.0.1/", "http://192.168.0.10/", "http://169.254.169.254/latest/meta-data", "http://2130706433/",
        "http://0x7f.1/", "http://127.1/", "http://metadata.google.internal/", "http://site.local/",
        "http://공개.kr\\@10.0.0.1", "http://user@site.kr/", "http://[::1]/", "http://localhost/",
    ):  # fmt: skip
        assert normalize_site_url(bad) is None, bad
    assert normalize_site_url("www.prugio.com") == "http://www.prugio.com/"
    assert normalize_site_url("https://8.8.8.8/") == "https://8.8.8.8/"


def test_minor23_extract_requests_split_by_text_limit() -> None:
    def cand(field: str, excerpt: str) -> FieldCandidate:
        return FieldCandidate(
            entity="complex_type", entity_id=None, entity_key="k:84A", field=field, value_text=None, value=None,
            source_rank=1, source_kind="notice_pdf", primary=True, label="확인 불가", excerpt=excerpt,
            excerpt_start=0, excerpt_end=1, raw_document_id=1, url="https://x", checked_at="2026-10-09",
            needs_extract=True,
        )  # fmt: skip

    cands = [cand(f"f{i}", f"발췌{i} " + "가" * 900) for i in range(5)]
    reqs = build_extract_requests(cands, max_text=2000)
    assert [r.fields for r in reqs] == [["f0", "f1"], ["f2", "f3"], ["f4"]]
    joined = "".join(r.text for r in reqs)
    for i in range(5):
        assert f"발췌{i}" in joined, "뒤 필드 발췌도 판정기에 간다"
    assert all(len(r.text) <= 2000 for r in reqs)


def test_minor24_invalid_news_items_are_recorded(db_session: Session, add_raw: AddRaw, region: Region, monkeypatch: Any) -> None:
    import json

    from app.normalize import catalyst as cat_mod

    body = {"items": [{"title": "역 신설 확정", "link": "ftp://bad.example/1", "description": "x", "pubDate": "Wed, 08 Oct 2026 09:00:00 +0900"}]}
    raw = add_raw(json.dumps(body, ensure_ascii=False), source_kind="news", url="https://naverapihub/news?q=x", region_id=region.id)
    out = cat_mod.catalysts_from_news(db_session, region.id, [raw])
    assert out.inserted == 0
    st = out.stats()
    assert st.get("invalid") == 1 and st["invalid_items"][0]["reason"], st
