"""R3e CORE3 — 5차 리뷰 백엔드 minor(정규화·보안·설정) (계약 2026-10-09.10).

| 리뷰 minor | 테스트 |
| --- | --- |
| `_text.py` IDNA 무시 문자·%00 | ``test_site_url_rejects_idna_ignored_chars_and_nul`` |
| 이름 키 NFKC 순서·로마 숫자·블럭/BL | ``test_name_key_keeps_phase_variants``·``test_apt_name_key_variants`` |
| `redact.py` 패턴 | ``test_redact_more_secret_keys_and_lowercase_bearer`` |
| BACKUP_DIR settings | ``test_backup_dir_reads_env_file`` |
| `notice_parser` 원 번호·재공급 | ``test_notice_number_order_and_resupply_kind`` |
| `living_area` 모호 법정동 | ``test_ambiguous_legal_dong_is_range_boundary`` |
| `price_view` low 음수 | ``test_discount_larger_than_floor_price_is_not_subtracted`` |
"""

# ruff: noqa: E501

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.orm import Session

FIX = Path(__file__).parent / "fixtures" / "notice"


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1­/",
        "http://foo.loc­alhost/",
        "http://127.0.0.1​/",
        "http://127.0.0.1᠋/",
        "http://127.0.0.1︀/",
        "http://127.0.0.1⁠/",
        "http://127.0.0.1͏/",
        "http://foo.local‍host/",
        "http://127.0.0.1%00.example.com/",
        "http://example.com/%00",
    ],
)
def test_site_url_rejects_idna_ignored_chars_and_nul(url: str) -> None:
    from app.normalize._text import normalize_site_url

    assert normalize_site_url(url) is None, url


def test_site_url_public_host_with_ignored_char_is_canonical() -> None:
    from app.normalize._text import normalize_site_url

    assert normalize_site_url("http://exam­ple.com/") == "http://example.com/"


@pytest.mark.parametrize(
    ("name", "want"),
    [
        ("J(2블럭 잔여세대)", "J(2블럭)"),
        ("M(II 잔여세대)", "M(II)"),
        ("S(3bl 무순위)", "S(3bl)"),
        ("F(A-3BL 무순위)", "F(A-3BL)"),
        ("T(Ⅱ-1 잔여세대)", "T(Ⅱ-1)"),
        ("한강 센트럴(Ⅱ 잔여세대)", "한강 센트럴(Ⅱ)"),
        ("C(무순위 2차)", "C"),  # 공급 회차는 뗀다
        ("I-Park(무순위)", "I-Park"),
    ],
)
def test_name_key_keeps_phase_variants(name: str, want: str) -> None:
    from app.normalize._text import strip_supply_round

    assert strip_supply_round(name) == want


def test_apt_name_key_variants() -> None:
    from app.normalize.benchmark import normalize_apt_name as nk
    from app.normalize.remaining import remainder_name_key

    # NFKC 전에 공급 구분 괄호를 떼므로 로마 숫자 단지가 남는다(Ⅱ·Ⅲ·없음 이 서로 다른 키)
    keys = {nk("한강(Ⅱ 잔여세대)"), nk("한강(Ⅲ 잔여세대)"), nk("한강(잔여세대)")}
    assert len(keys) == 3, keys
    assert len({remainder_name_key("한강(Ⅱ 잔여세대)"), remainder_name_key("한강(Ⅲ 잔여세대)")}) == 2
    # 블록 표기 변형은 같은 블록
    assert nk("검단 AA13-1BL") == nk("검단 AA13-1블록") == nk("검단 AA13-1블럭") == nk("검단 AA13-1 bl")
    assert nk("검단 AA1-31블록") != nk("검단 AA13-1블록")


@pytest.mark.parametrize(
    ("text", "secret"),
    [
        ("aws_secret_access_key=AKIA1234", "AKIA1234"),
        ("private_key=AAAAB3", "AAAAB3"),
        ("pwd=hunter2", "hunter2"),
        ("bearer abc123", "abc123"),
        ("BEARER abc123", "abc123"),
    ],
)
def test_redact_more_secret_keys_and_lowercase_bearer(text: str, secret: str) -> None:
    from app.core.redact import redact_text

    out = redact_text(text)
    assert secret not in out and "[REDACTED" in out, out


def test_redact_keeps_plain_words() -> None:
    from app.core.redact import redact_text

    for t in ("the bearer of news", "token_type=bearer", "Bearer abcdefg"):
        assert redact_text(t) == t


def test_backup_dir_reads_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.settings import Settings, env_var_names
    from app.scheduler.backup import backup_dir

    for n in [*env_var_names(), "BACKUP_DIR"]:
        monkeypatch.delenv(n, raising=False)
    env = tmp_path / ".env"
    env.write_text(
        f"DATABASE_URL=sqlite:///{(tmp_path / 'x.db').as_posix()}\nRAW_DIR={(tmp_path / 'raw').as_posix()}\n"
        f"BACKUP_DIR={(tmp_path / 'mybackups').as_posix()}\n",
        encoding="utf-8",
    )
    s = Settings(_env_file=env)  # type: ignore[call-arg]
    assert backup_dir(s) == tmp_path / "mybackups"
    empty = tmp_path / "empty.env"
    empty.write_text(f"RAW_DIR={(tmp_path / 'raw').as_posix()}\nBACKUP_DIR=\n", encoding="utf-8")
    assert backup_dir(Settings(_env_file=empty)) == (tmp_path / "raw").resolve().parent / "backup"  # type: ignore[call-arg]


def _raw() -> Any:
    from app.core.contracts_gen import RawDocument

    return RawDocument(id=1, source_kind="notice_pdf", url="https://static.applyhome.co.kr/x.pdf",
                       fetched_at="2026-10-09T00:00:00+09:00", http_status=200, sha256="0" * 64, region_id=1, path=None,
                       content_type=None, text_path=None, complex_id=None)  # fmt: skip


def test_notice_number_order_and_resupply_kind() -> None:
    from app.normalize.notice_parser import parse_notice_text

    text = (FIX / "2026940173_elif_imui3.txt").read_text(encoding="utf-8")
    lines = text.split("\n")
    i_this = next(i for i, ln in enumerate(lines) if "주택관리번호는 2026940173" in ln and "최초" not in ln)
    i_orig = next(i for i, ln in enumerate(lines) if "최초 주택관리번호는" in ln)
    lines[i_this], lines[i_orig] = lines[i_orig], lines[i_this]
    keys = {c.entity_key for c in parse_notice_text("\n".join(lines), _raw()) if c.entity == "payment_terms"}
    assert keys == {"2025000302:2026940173"}, keys  # 원 단지 번호 : 이 공고 번호 — 줄 순서와 무관
    resupply = text.replace("임의공급 (3차) 입주자모집공고", "재공급 입주자모집공고", 1)
    kinds = {c.value for c in parse_notice_text(resupply, _raw()) if c.field == "notice_kind"}
    assert kinds == {"무순위"}, kinds  # '재공급' 제목이 '본청약'이 아니다


def test_ambiguous_legal_dong_is_range_boundary(db_session: Session, region: Any) -> None:
    """같은 이름 읍면동이 지역 안 두 시군구에 있어 법정동을 정할 수 없으면, 이미 분류된 단지도 '범위 경계'(판정 범위 제외)."""
    from app.models import Complex, LegalDong
    from app.normalize.living_area import assign_complex_area

    a = LegalDong(code="2818599901", sido_name="인천광역시", sigungu_name="연수구", eupmyeondong_name="겹친동",
                  ri_name=None, full_name="인천광역시 연수구 겹친동", sigungu_code="28185", active=True, source_date="2026-10-01")  # fmt: skip
    b = LegalDong(code="2824599901", sido_name="인천광역시", sigungu_name="계양구", eupmyeondong_name="겹친동",
                  ri_name=None, full_name="인천광역시 계양구 겹친동", sigungu_code="28245", active=True, source_date="2026-10-01")  # fmt: skip
    db_session.add_all([a, b])
    region.legal_dong_codes = [*(region.legal_dong_codes or []), a.code, b.code]
    cx = Complex(region_id=region.id, applyhome_id="2026777001", name="겹친동 단지", former_names=[], apply_dates=[],
                 contract_dates=[], inclusion_class="private_sale_apt", address="인천광역시 겹친동 1-1")  # fmt: skip
    db_session.add(cx)
    db_session.flush()
    res = assign_complex_area(db_session, cx)
    assert res.legal_dong_code is None and not res.in_region
    assert cx.inclusion_class == "범위 경계"


def test_discount_larger_than_floor_price_is_not_subtracted() -> None:
    """확인됨 할인이 대표층가보다 크고 최고가보다 작으면 low 가 음수가 됐다 — 빼지 않는다(applied False)."""
    from types import SimpleNamespace

    from app.analysis.price_view import current_price

    t = SimpleNamespace(id=1, type_code="84A", area_m2=84.9, max_price_won=600_000_000,
                        floor_sample_price_won=300_000_000, balcony_won=None, options_required_won=None)  # fmt: skip
    p = SimpleNamespace(id=7, effective_from="2026-09-01", notice_no="n", price_by_type={},
                        discount_by_type={"84A": 350_000_000})  # fmt: skip
    v = current_price([t], [p], discount_label=lambda r: "확인됨")  # type: ignore[list-item]
    assert not v.discount_applied and v.low_won == 300_000_000 and v.high_won == 600_000_000
    p.discount_by_type = {"84A": 10_000_000}
    v = current_price([t], [p], discount_label=lambda r: "확인됨")  # type: ignore[list-item]
    assert v.discount_applied and v.low_won == 290_000_000 and v.low_won > 0
