"""인천·김포 회귀 픽스처 생성기 (WP9) → contracts/fixtures/incheon_gimpo_2026-10-08/

사용 (backend/ 에서, app 패키지를 import 하므로):
    uv run python ../contracts/fixtures/tools/build_incheon_gimpo.py           # 다시 쓴다
    uv run python ../contracts/fixtures/tools/build_incheon_gimpo.py --check   # 커밋된 파일과 다르면 exit 1

만드는 것: region.json, complexes.json, provenance.json, snapshots.json, judgments/(_meta·_index·<tool>/<hex>.json),
raw/(documents.json, 재구성 발췌 txt, 팝업 PNG, 목록 녹화, rtms, T3·T5·T6·T13·T14·T18 입력).
만들지 않는 것: expected_scores.json(WP0-A 시드), expected_scores_v2.json(WP4), README.md(손으로 쓴다).
"""

# ruff: noqa: E501  (원문 표기)
from __future__ import annotations

import argparse
import copy
import json
import sys
import zipfile
from pathlib import Path
from typing import Any

TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parents[2]
FIXTURE = REPO / "contracts" / "fixtures" / "incheon_gimpo_2026-10-08"
sys.path.insert(0, str(TOOLS))

from fixture_lib import CHECKED, FETCHED_AT, J, Registry, dumps, png_bytes, raw_doc, sha256_hex  # noqa: E402
from hash import fixture_hash  # noqa: E402
from incheon_gimpo_complexes import COMPLEXES  # noqa: E402
from incheon_gimpo_complexes_b import COMPLEXES_B  # noqa: E402
from incheon_gimpo_judgments import CALLS, INTEGRATED_DECIDES, add  # noqa: E402

ADAPTER_VERSION = "mock-fixture-2026-10-08"
REGION_ID = 1
SNAPSHOT_INCHEON, SNAPSHOT_MERGED = 11, 12
COMPLEX_FIELDS = ["housing_type", "land_type", "price_cap", "regulated", "units_total", "units_general", "units_special",
                  "officetel_units", "notice_date"]  # fmt: skip
TAIL_FIELDS = ["move_in_ym", "resale_months", "resale_end", "resale_release_on_registration", "residency_months",
               "rewin_restriction_years"]  # fmt: skip

# 법정동 코드: 행정표준코드관리시스템 '법정동코드 전체자료' 공식 사본(contracts/fixtures/reference/legal_dong_full.zip,
# WP1b reference 수집기가 2026-10-09 받은 파일 — manifest.json). 2026-07 분구로 서구(28260)와 그 법정동은 폐지,
# 검단 법정동은 검단구(28290) 현행 코드다(계약 2026-10-09.2). 발췌는 legal_dong_excerpt()가 공식 사본에서 그대로 뽑는다.
LEGAL_DONG_SOURCE = "https://www.code.go.kr/etc/codeFullDown.do?codeseId=법정동코드"
LEGAL_DONG_COPY = REPO / "contracts" / "fixtures" / "reference" / "legal_dong_full.zip"
SONGDO = [("2818510600", "인천광역시 연수구 송도동")]
GEOMDAN = [("2829010100", "백석동"), ("2829010200", "시천동"), ("2829010300", "마전동"), ("2829010400", "당하동"),
           ("2829010500", "원당동"), ("2829010600", "대곡동"), ("2829010700", "금곡동"), ("2829010800", "오류동"),
           ("2829010900", "왕길동"), ("2829011000", "불로동")]  # fmt: skip
GEOMDAN_OLD_PREFIX = "28260"  # 폐지된 서구 코드(발췌에 폐지 행으로 함께 남긴다)
GYEYANG_CODES = [
    ("2824510100", "효성동"),
    ("2824510200", "계산동"),
    ("2824510300", "작전동"),
    ("2824510400", "서운동"),
    ("2824510500", "임학동"),
    ("2824510600", "용종동"),
    ("2824510700", "병방동"),
    ("2824510800", "방축동"),
    ("2824510900", "박촌동"),
    ("2824511000", "동양동"),
    ("2824511100", "귤현동"),
    ("2824511200", "상야동"),
    ("2824511300", "하야동"),
    ("2824511400", "평동"),
    ("2824511500", "노오지동"),
    ("2824511600", "선주지동"),
    ("2824511700", "이화동"),
    ("2824511800", "오류동"),
    ("2824511900", "갈현동"),
    ("2824512000", "둑실동"),
    ("2824512100", "목상동"),
    ("2824512200", "다남동"),
    ("2824512300", "장기동"),
]
GIMPO_CODES = [
    ("4157010100", "북변동"),
    ("4157010200", "걸포동"),
    ("4157010300", "운양동"),
    ("4157010400", "장기동"),
    ("4157010500", "감정동"),
    ("4157010600", "사우동"),
    ("4157010700", "풍무동"),
    ("4157010800", "마산동"),
    ("4157010900", "구래동"),
    ("4157025000", "통진읍"),
    ("4157025021", "통진읍 도사리"),
    ("4157025022", "통진읍 마송리"),
    ("4157025023", "통진읍 서암리"),
    ("4157025024", "통진읍 수참리"),
    ("4157025025", "통진읍 가현리"),
    ("4157025026", "통진읍 동을산리"),
    ("4157025027", "통진읍 귀전리"),
    ("4157025028", "통진읍 고정리"),
    ("4157025029", "통진읍 옹정리"),
    ("4157025300", "고촌읍"),
    ("4157025321", "고촌읍 향산리"),
    ("4157025322", "고촌읍 풍곡리"),
    ("4157025323", "고촌읍 태리"),
    ("4157025324", "고촌읍 신곡리"),
    ("4157025325", "고촌읍 전호리"),
    ("4157025600", "양촌읍"),
    ("4157025621", "양촌읍 양곡리"),
    ("4157025622", "양촌읍 누산리"),
    ("4157025623", "양촌읍 석모리"),
    ("4157025624", "양촌읍 구래리"),
    ("4157025625", "양촌읍 대포리"),
    ("4157025626", "양촌읍 학운리"),
    ("4157025627", "양촌읍 유현리"),
    ("4157025628", "양촌읍 흥신리"),
    ("4157034000", "대곶면"),
    ("4157034021", "대곶면 대능리"),
    ("4157034022", "대곶면 대벽리"),
    ("4157034023", "대곶면 약암리"),
    ("4157034024", "대곶면 상마리"),
    ("4157034025", "대곶면 율생리"),
    ("4157034026", "대곶면 초원지리"),
    ("4157034027", "대곶면 거물대리"),
    ("4157034028", "대곶면 오니산리"),
    ("4157034029", "대곶면 송마리"),
    ("4157034030", "대곶면 석정리"),
    ("4157034031", "대곶면 쇄암리"),
    ("4157034032", "대곶면 신안리"),
    ("4157034033", "대곶면 대명리"),
    ("4157035000", "월곶면"),
    ("4157035021", "월곶면 군하리"),
    ("4157035022", "월곶면 고막리"),
    ("4157035023", "월곶면 갈산리"),
    ("4157035024", "월곶면 고양리"),
    ("4157035025", "월곶면 포내리"),
    ("4157035026", "월곶면 성동리"),
    ("4157035027", "월곶면 보구곶리"),
    ("4157035028", "월곶면 용강리"),
    ("4157035029", "월곶면 조강리"),
    ("4157035030", "월곶면 개곡리"),
    ("4157036000", "하성면"),
    ("4157036021", "하성면 마곡리"),
    ("4157036022", "하성면 석탄리"),
    ("4157036023", "하성면 후평리"),
    ("4157036024", "하성면 시암리"),
    ("4157036025", "하성면 마조리"),
    ("4157036026", "하성면 가금리"),
    ("4157036027", "하성면 양택리"),
    ("4157036028", "하성면 원산리"),
    ("4157036029", "하성면 하사리"),
    ("4157036030", "하성면 봉성리"),
    ("4157036031", "하성면 전류리"),
    ("4157036032", "하성면 마근포리"),
]
HOUSEHOLDS_UNKNOWN = "주민등록 세대 현황 파일 미수집(contracts/fixtures/reference 없음)"


# ---------------------------------------------------------------- region


def build_region() -> dict[str, Any]:
    la = [
        ("la_1", "연수구", [c for c, _ in SONGDO]),
        ("la_2", "검단구", [c for c, _ in GEOMDAN]),
        ("la_3", "계양구", [c for c, _ in GYEYANG_CODES]),
        ("la_4", "김포시", [c for c, _ in GIMPO_CODES]),
    ]
    living_areas = [
        {"id": i, "name": n, "legal_dong_codes": codes,
         "households": {"v": None, "label": "확인 불가", "reason": HOUSEHOLDS_UNKNOWN, "prov": None, "checked_at": CHECKED},
         "supply_ref_units": None}
        for i, n, codes in la
    ]  # fmt: skip
    selections = [{"kind": "legal_dong", "code": SONGDO[0][0], "full_name": SONGDO[0][1]}]
    selections += [{"kind": "legal_dong", "code": c, "full_name": f"인천광역시 검단구 {n}"} for c, n in GEOMDAN]
    selections += [{"kind": "sigungu", "code": "28245", "full_name": "인천광역시 계양구"},
                   {"kind": "sigungu", "code": "41570", "full_name": "경기도 김포시"}]  # fmt: skip
    return {
        "id": REGION_ID,
        "name": "인천 송도·검단·계양 + 김포",
        "query_text": "송도, 검단, 계양구, 김포시",
        "selections": selections,
        "sido_codes": ["28", "41"],
        "sigungu_codes": ["28185", "28245", "28290", "41570"],
        "legal_dong_codes": [c for _, _, codes in la for c in codes],
        "living_areas": living_areas,
        "age_premium_coef": {"c_per_year": 0.015, "cap_years": 8, "label": "추정"},
        "supply_ref_pct": 0.08,
        "applyhome_query": {"sido_codes": ["28", "41"], "from_ym": "2024-01"},
        "status": "ready",
        "created_at": "2026-10-07T00:00:00+09:00",
        "latest_snapshot": None,
    }


# ---------------------------------------------------------------- complexes


def build_bundle(reg: Registry, spec: dict[str, Any]) -> dict[str, Any]:
    cid = spec["id"]
    for key, (kind, url, title) in spec["sources"].items():
        reg.source(cid, key, kind, url, title)

    def f(s: Any, entity: str, field: str) -> Any:
        return reg.fact(cid, s, entity, field)

    c = spec["c"]
    complex_: dict[str, Any] = {
        "id": cid,
        "region_id": REGION_ID,
        "applyhome_id": spec["applyhome_id"],
        "name": spec["name"],
        "former_names": spec["former_names"],
        "address": spec["address"],
        "legal_dong_code": spec["legal_dong_code"],
        "living_area": spec["living_area"],
        "living_area_name": spec["living_area_name"],
        "official_site_url": spec["official_site_url"],
        "developer": spec["developer"],
        "trustee": spec["trustee"],
        "builder": spec["builder"],
    }
    for name in COMPLEX_FIELDS:
        complex_[name] = f(c[name], "complex", name)
    complex_["apply_dates"] = [
        {
            "kind": k,
            "start": f(s, "complex", "apply_dates"),
            "end": f(e, "complex", "apply_dates") if e else None,
        }
        for k, s, e in spec["apply_dates"]
    ]
    complex_["winner_date"] = f(c["winner_date"], "complex", "winner_date")
    complex_["contract_dates"] = [
        {
            "kind": k,
            "start": f(s, "complex", "contract_dates"),
            "end": f(e, "complex", "contract_dates") if e else None,
        }
        for k, s, e in spec["contract_dates"]
    ]
    for name in TAIL_FIELDS:
        complex_[name] = f(c[name], "complex", name) if c[name] is not None else None
    cls, decision, prob = spec["inclusion"]
    assert isinstance(prob, J)
    complex_["inclusion_class"] = cls
    complex_["inclusion_decision"] = decision
    complex_["inclusion_prob"] = f(prob, "complex", "inclusion_prob")
    complex_["track"] = spec["track"]

    types = []
    for t in spec["types"]:
        types.append(
            {
                "id": None,
                "complex_id": cid,
                "type_code": t["type_code"],
                "area_m2": f(t["area"], "complex_type", "area_m2"),
                "units": f(t["units"], "complex_type", "units"),
                "max_price_won": f(t["max"], "complex_type", "max_price_won"),
                "floor_sample_price_won": f(t["floor"], "complex_type", "floor_sample_price_won"),
                "floor_sample_text": t["floor_text"],
                "balcony_won": f(t["balcony"], "complex_type", "balcony_won"),
                "options_required_won": f(t["options"], "complex_type", "options_required_won"),
                "options_text": t["options_text"],
                "is_basis": t["is_basis"],
            }
        )
    assert sum(1 for t in types if t["is_basis"]) == (1 if types else 0), spec["key"]

    payment = []
    for p in spec["payment"]:
        change = None
        if p["change"]:
            change = {
                "down_payment_pct_delta": f(p["change"]["down"], "payment_terms", "down_payment_pct")
                if p["change"]["down"]
                else None,
                "price_change_pct": f(p["change"]["price"], "payment_terms", "price_change_pct")
                if p["change"]["price"]
                else None,
            }
        payment.append(
            {
                "id": None,
                "complex_id": cid,
                "notice_no": p["notice_no"],
                "notice_kind": p["notice_kind"],
                "effective_from": f(p["effective_from"], "payment_terms", "effective_from"),
                "down_payment_pct": f(p["down"], "payment_terms", "down_payment_pct"),
                "down_payment_first_won": f(p["first"], "payment_terms", "down_payment_first_won"),
                "interim_pct": f(p["interim"], "payment_terms", "interim_pct"),
                "interim_terms_text": p["interim_text"],
                "balance_pct": f(p["balance"], "payment_terms", "balance_pct"),
                "interim_schedule": [
                    {
                        "seq": seq,
                        "due_date": f(due, "payment_terms", "interim_schedule"),
                        "pct": f(pct, "payment_terms", "interim_schedule"),
                    }
                    for seq, due, pct in p["schedule"]
                ],
                "is_current": p["is_current"],
                "change_vs_first": change,
            }
        )

    competition = [
        {"id": None, "complex_id": cid, "round": r["round"], "kind": r["kind"], "type_code": r["type_code"],
         "supply": f(r["supply"], "competition", "supply"), "applied": f(r["applied"], "competition", "applied"),
         "ratio_or_shortfall_text": r["ratio"], "raw_document_id": f"@doc:{cid}:{r['doc']}" if r["doc"] else None}
        for r in spec["competition"]
    ]  # fmt: skip
    events = [
        {"id": None, "complex_id": cid, "kind": e["kind"], "notice_no": e["notice_no"],
         "notice_date": f(e["notice_date"], "remaining_event", "notice_date"),
         "apply_dates": [f(a, "remaining_event", "apply_dates") for a in e["apply_dates"]],
         "units": f(e["units"], "remaining_event", "units"), "units_by_type": e["units_by_type"],
         "ratio_text": e["ratio_text"], "result_text": e["result_text"],
         "raw_document_id": f"@doc:{cid}:{e['doc']}" if e["doc"] else None}
        for e in spec["events"]
    ]  # fmt: skip
    intake = []
    for it in spec["intake"]:
        doc = it["doc"]
        ref = None
        if doc is not None:
            ref = doc if doc.startswith("@") else f"@doc:{cid}:{doc}"
        intake.append(
            {
                "id": None,
                "complex_id": cid,
                "snapshot_id": SNAPSHOT_MERGED,
                "status": it["status"],
                "path": it["path"],
                "evidence_url": it["evidence_url"],
                "screenshot_path": None,
                "raw_document_id": ref,
                "checked_at": CHECKED,
                "http_status": it["http_status"],
                "reason": it["reason"],
                "note": it["note"],
                "entered_by": None,
            }
        )
    return {
        "fixture_key": spec["key"],
        "complex": complex_,
        "types": types,
        "payment_terms": payment,
        "competition": competition,
        "remaining_events": events,
        "intake": intake,
    }


# ---------------------------------------------------------------- raw extras (T3·T8·T17 등)

ELIF_SITE = "https://xn--c79an5jqrb8zf6rcfy4a5qw65b.com/"
CANTAVIL_SITE = "https://cantaviltheedition.com/"
POPUP_ELIF = png_bytes(24, 16, (20, 90, 160), (250, 250, 250))
POPUP_ELIF_CHANGED = png_bytes(24, 16, (160, 40, 40), (250, 250, 250))
POPUP_CANTAVIL = png_bytes(24, 16, (30, 120, 60), (240, 240, 240))


def extra_documents(reg: Registry) -> dict[str, dict[str, Any]]:
    """텍스트 발췌가 아닌 원문 행: 실패(403·DNS·접속 실패), 팝업 스크린샷, 청약홈 목록, rtms, 참조 사본."""
    out: dict[str, dict[str, Any]] = {}

    def add_doc(ref: str, doc: dict[str, Any]) -> None:
        doc["_ref"] = ref
        reg.extra_docs.append(doc)
        out[ref] = doc

    add_doc(
        "@fail:switzen",
        raw_doc(None, "official_site", "https://opus-switzen.com/", None, None, 4, http_status=403),
    )
    add_doc(
        "@fail:gnheim",
        raw_doc(
            None,
            "official_site",
            "https://사우역지엔하임.com/",
            None,
            None,
            14,
            http_status=None,
            error_text="DNS",
        ),
    )
    add_doc(
        "@fail:harrington",
        raw_doc(
            None,
            "official_site",
            "https://해링턴플레이스풍무.com/",
            None,
            None,
            13,
            http_status=None,
            error_text="timeout",
        ),
    )
    for key, site, data, cid in [
        ("elif", ELIF_SITE, POPUP_ELIF, 2),
        ("cantavil", CANTAVIL_SITE, POPUP_CANTAVIL, 7),
    ]:
        path = f"official_site/{key}_popup_2026-10-07.png"
        reg.files[path] = data
        add_doc(f"@popup:{key}", raw_doc(None, "official_site", site, path, data, cid, content_type="image/png",
                                         image_hash=sha256_hex(data), text_path=None))  # fmt: skip
    listing = applyhome_list_bytes()
    reg.files["applyhome_list/2026-10-07.json"] = listing
    reg.files["applyhome_list/2026-10-08.json"] = listing
    add_doc("@list:2026-10-07", raw_doc(None, "applyhome_list", "https://www.applyhome.co.kr/ai/aia/selectAPTLttotPblancListView.do",
                                        "applyhome_list/2026-10-07.json", listing, None, content_type="application/json"))  # fmt: skip
    ref_text = legal_dong_excerpt()
    reg.files["reference/legal_dong_excerpt.tsv"] = ref_text
    add_doc("@ref:legal_dong", raw_doc(None, "reference", LEGAL_DONG_SOURCE, "reference/legal_dong_excerpt.tsv", ref_text, None,
                                       content_type="text/tab-separated-values; charset=utf-8"))  # fmt: skip
    return out


def applyhome_list_bytes() -> bytes:
    items = [{"house_manage_no": b["applyhome_id"], "name": b["name"], "address": b["address"]}
             for b in sorted(COMPLEXES + COMPLEXES_B, key=lambda x: x["id"]) if b["applyhome_id"]]  # fmt: skip
    doc = {
        "source": "청약홈 APT 분양정보 목록(공급지역 인천·경기) 녹화 — 보고서 단지만 발췌",
        "checked_at": CHECKED,
        "items": items,
    }
    return dumps(doc).encode("utf-8")


def official_legal_dong_rows() -> dict[str, tuple[str, str]]:
    """공식 사본(cp949 탭 구분 txt) → {코드: (법정동명, 폐지여부)}."""
    with zipfile.ZipFile(LEGAL_DONG_COPY) as z:
        text = z.read(z.namelist()[0]).decode("cp949")
    rows: dict[str, tuple[str, str]] = {}
    for line in text.splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) >= 3:
            rows[parts[0].strip()] = (parts[1].strip(), parts[2].strip())
    return rows


def legal_dong_excerpt() -> bytes:
    """픽스처 지역의 법정동 행을 공식 사본에서 그대로 발췌한다(+ 검단의 폐지 서구 코드 행). 이름·존재 여부가
    생성기 표와 다르면 실패한다 — 손으로 적은 코드가 공식 표와 어긋나지 않게."""
    rows = official_legal_dong_rows()
    wanted = [(c, n) for c, n in SONGDO]
    wanted += [(c, f"인천광역시 검단구 {n}") for c, n in GEOMDAN]
    wanted += [(c, f"인천광역시 계양구 {n}") for c, n in GYEYANG_CODES]
    wanted += [(c, f"경기도 김포시 {n}") for c, n in GIMPO_CODES]
    lines = ["# 법정동코드 전체자료 발췌(행정표준코드관리시스템 공식 사본 contracts/fixtures/reference/legal_dong_full.zip, "
             "공공누리 1유형). 원천: " + LEGAL_DONG_SOURCE,
             "# 2026-07 분구: 서구(28260) 폐지 → 검단구(28290)·서해구 신설. 검단 법정동은 검단구 현행 코드, 옛 서구 코드는 폐지 행으로 함께 둔다. "
             "확인일 2026-10-09.",
             "법정동코드\t법정동명\t폐지여부"]  # fmt: skip
    for code, name in wanted:
        got = rows.get(code)
        if got != (name, "존재"):
            raise SystemExit(f"공식 사본과 다름: {code} {name} → {got}")
        lines.append(f"{code}\t{name}\t존재")
    old_names = {f"인천광역시 서구 {n}" for _, n in GEOMDAN} | {"인천광역시 서구 불노동"}
    old = sorted(c for c, (n, _) in rows.items() if c.startswith(GEOMDAN_OLD_PREFIX) and n in old_names)
    for code in old:
        name, status = rows[code]
        if status != "폐지":
            raise SystemExit(f"서구 코드가 폐지가 아님: {code} {name} {status}")
        lines.append(f"{code}\t{name}\t{status}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def resolve_refs(node: Any, refs: dict[str, int]) -> Any:
    if isinstance(node, dict):
        return {k: resolve_refs(v, refs) for k, v in node.items()}
    if isinstance(node, list):
        return [resolve_refs(v, refs) for v in node]
    if isinstance(node, str) and node.startswith("@"):
        return refs[node]
    return node


# ---------------------------------------------------------------- rtms (T4, T11)


def trade(apt: str, year: int, area: float, floor: int | None, price: int, date: str) -> dict[str, Any]:
    return {"id": None, "living_area": "la_4", "apt_name": apt, "completed_year": year, "area_m2": area, "floor": floor,
            "price_won": price, "deal_date": date, "cancelled": False, "source": "reprocessed", "is_presale": False}  # fmt: skip


def rtms_t4() -> dict[str, Any]:
    apt = "한강메트로자이 2단지"
    rows = [
        trade(apt, 2020, 84.0, 30, 680_000_000, "2026-09-18"),  # 보고서: 09-18 30층 6.8억
        trade(apt, 2020, 84.0, None, 590_000_000, "2026-04-15"),  # 보고서 범위 하단 5.9억(날짜·층 합성)
        trade(apt, 2020, 84.0, None, 600_000_000, "2026-05-07"),
        trade(apt, 2020, 84.0, None, 610_000_000, "2026-05-28"),
        trade(apt, 2020, 84.0, None, 620_000_000, "2026-06-11"),
        trade(apt, 2020, 84.0, None, 630_000_000, "2026-06-30"),
        trade(apt, 2020, 84.0, None, 640_000_000, "2026-07-14"),
        trade(apt, 2020, 84.0, None, 650_000_000, "2026-08-02"),
        trade(apt, 2020, 84.0, None, 660_000_000, "2026-08-21"),
        trade(apt, 2020, 84.0, None, 670_000_000, "2026-09-05"),
        trade(
            apt, 2020, 84.0, None, 1_100_000_000, "2026-09-24"
        ),  # 이상치(보고서: 11억 2021-09-24, 타입 오류 가능성)
    ]
    return {
        "case": "T4",
        "description": "메트로자이 2단지 84㎡ 거래 중 1건만 크게 벗어남(11억, 타입 오류 의심) → 1.5×IQR 이상치 제외 + comparable_set '이상치 제외' 기록, 원본 행 유지",
        "apt_name": apt,
        "source_url": "https://dapt.kr/apt/BjA163.html",
        "label": "재가공",
        "checked_at": CHECKED,
        "reported": {
            "range_won": [590_000_000, 680_000_000],
            "count": 10,
            "latest": "2026-09-18 30층 6.8억",
            "peak": "11억(2021-09-24, 타입 오류 가능성 — 보고서 §12-3-1·§12-6-3)",
        },
        "synthetic_rows": {
            "1-9": "보고서는 범위(5.9~6.8억, 10건)만 기재 — 개별 거래 가격·날짜는 범위 안에서 합성",
            "10": "11억 거래는 보고서상 2021-09-24. T4 재현을 위해 비교 창(기준일 이전 6개월) 안 2026-09-24로 옮긴 테스트 변형",
        },
        "area_note": "전용 84㎡형(소수점 보고서 미기재)",
        "trades": rows,
    }


def rtms_t11() -> dict[str, Any]:
    rows = [
        trade("힐스테이트 리버시티 1단지", 2020, 84.0, 7, 580_000_000, "2026-09-14"),  # 보고서
        trade(
            "힐스테이트 리버시티 1단지", 2020, 84.0, None, 610_000_000, "2026-06-10"
        ),  # 범위 상단(합성 날짜)
        trade("힐스테이트 리버시티 2단지", 2020, 84.0, 11, 590_000_000, "2026-09-20"),  # 보고서
        trade(
            "힐스테이트 리버시티 2단지", 2020, 84.91, None, 587_000_000, "2026-08-04"
        ),  # 뉴데일리 2026-08-19
        trade(
            "힐스테이트 리버시티 2단지", 2020, 84.0, None, 560_000_000, "2026-05-12"
        ),  # 범위 하단(합성 날짜)
        trade(
            "힐스테이트 리버시티 2단지", 2020, 84.0, None, 630_000_000, "2026-07-08"
        ),  # 범위 상단(합성 날짜)
        trade("고촌 센트럴자이", 2024, 84.0, 6, 750_000_000, "2026-09-05"),  # 보고서
        trade("고촌 센트럴자이", 2024, 84.0, 11, 780_000_000, "2026-04-10"),  # 보고서
        trade("고촌 센트럴자이", 2024, 84.0, None, 740_000_000, "2026-06-22"),  # 범위 하단(합성 날짜)
    ]
    return {
        "case": "T11",
        "description": "스위첸(고촌 향산리) 비교군: 같은 산단 신축 입주 거래 0건 → 리버시티(2020)·고촌 센트럴자이(2024) 대체, 보정·미보정 중앙값 둘 다, 라벨 '추정(대체·보정 c=0.015)'",
        "target_complex_id": 4,
        "source_url": "https://dapt.kr/apt/BjA168.html",
        "source_urls": [
            "https://dapt.kr/apt/BjA168.html",
            "https://dapt.kr/apt/BjA176.html",
            "https://dapt.kr/apt/BjA205.html",
            "https://biz.newdaily.co.kr/site/data/html/2026/08/19/2026081900101.html",
        ],
        "label": "재가공",
        "checked_at": CHECKED,
        "reported": {
            "리버시티 1단지": "5.8~6.1억(8) · 09-14 7층 5.8억",
            "리버시티 2단지": "5.6~6.3억(10) · 09-20 11층 5.9억 · 08-04 84.91㎡ 5.87억",
            "고촌 센트럴자이": "7.4~7.8억(6) · 09-05 6층 7.5억, 04-10 11층 7.8억",
        },
        "synthetic_rows": {"1,4,5,8": "범위 끝값 — 가격은 보고서 범위, 날짜·층은 합성"},
        "trades": rows,
    }


# ---------------------------------------------------------------- T5 (해링턴 1,573 vs 1,769)

T5_DETAIL_URL = "https://www.applyhome.co.kr/ai/aia/selectAPTLttotPblancDetail.do?houseManageNo=2025000271&pblancNo=2025000271"
T5_NOTICE_URL = "https://static.applyhome.co.kr/ai/aia/getAtchmnfl.do?houseManageNo=2025000271&pblancNo=2025000271&atchmnflSeqNo=1553566&atchmnflSn=4"
T5_HEADER = ("# T5 상충 사례 입력(RA §9 T5 · meta_prompt §2-9 '해링턴 세대수 1,573 vs 1,769').\n"
             "# 1,573 = 보고서 §12-3-6 해링턴 1~3BL 합계(670+664+239). 1,769 = RA가 정의한 상충 값(원천 보고서 본문에 없음).\n")  # fmt: skip


def t5_files(reg: Registry) -> list[dict[str, Any]]:
    detail_line = "공급세대수 1,573세대"
    notice_line = "총 1,769세대"
    detail = (T5_HEADER + "# 원문: " + T5_DETAIL_URL + "\n" + detail_line + "\n").encode("utf-8")
    notice = (T5_HEADER + "# 원문: " + T5_NOTICE_URL + "\n" + notice_line + "\n").encode("utf-8")
    reg.files["t5_harrington/applyhome_detail.txt"] = detail
    reg.files["t5_harrington/notice.txt"] = notice
    d1 = raw_doc(None, "applyhome_detail", T5_DETAIL_URL, "t5_harrington/applyhome_detail.txt", detail, None)
    d2 = raw_doc(None, "notice_pdf", T5_NOTICE_URL, "t5_harrington/notice.txt", notice, None)
    d1["_ref"], d2["_ref"] = "@t5:detail", "@t5:notice"
    reg.extra_docs += [d1, d2]

    def cand(kind: str, rank: int, text: str, value: int, data: bytes, ref: str, url: str) -> dict[str, Any]:
        body = data.decode("utf-8")
        start = body.index(text)
        return {"entity": "complex", "entity_id": None, "entity_key": "applyhome_id:2025000271+2025000273+2025000274",
                "field": "units_total", "value_text": text.split()[-1], "value": value, "source_rank": rank,
                "source_kind": kind, "primary": True, "label": "확인됨", "reason": None, "excerpt": text,
                "excerpt_start": start, "excerpt_end": start + len(text), "raw_document_id": ref, "url": url,
                "checked_at": CHECKED, "needs_extract": False}  # fmt: skip

    return [
        cand("applyhome_detail", 1, detail_line, 1573, detail, "@t5:detail", T5_DETAIL_URL),
        cand("notice_pdf", 2, notice_line, 1769, notice, "@t5:notice", T5_NOTICE_URL),
    ]


# ---------------------------------------------------------------- judgments


def build_judgments(expected: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, bytes]]:
    ids = {c["key"]: c["complex_id"] for c in expected["complexes"]}
    if not any(c["seq"] == 125 for c in CALLS):
        for name, (seq, purpose, summary) in INTEGRATED_DECIDES.items():
            block = expected["decide_integrated"][name]

            def opt(key: str) -> str:
                return f"complex:{ids[key]}" if key in ids else key

            add(seq, "decide", purpose, {"situation": summary, "options": [opt(k) for k in block["checks"]] + ["ask_user", "investigate"]}, "ok",
                {"selected": opt(block["selected"]), "probs": {opt(k): v for k, v in block["probs"].items()},
                 "checks": {opt(k): v for k, v in block["checks"].items()}, "warnings": block["warnings"], "escaped": False, "question": None},
                confidence=block["confidence"], raw_extra={"requirement_order": block["requirement_order"],
                                                           "source": "expected_scores.json decide_integrated." + name})  # fmt: skip
    index: list[dict[str, Any]] = []
    files: dict[str, bytes] = {}
    for call in sorted(CALLS, key=lambda c: c["seq"]):
        h = fixture_hash(call["tool"], call["purpose"], call["payload"], ADAPTER_VERSION)
        rel = f"{call['tool']}/{h.removeprefix('sha256:')}.json"
        payload_text = json.dumps(call["payload"], sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        env = {
            "tool": call["tool"],
            "purpose": call["purpose"],
            "input_hash": h,
            "input_len": len(payload_text),
            "status": call["status"],
            "confidence": call["confidence"],
            "cached": False,
            "result": call["result"],
            "raw": call["raw"],
            "duration_ms": None,
            "judgment_seq": call["seq"],
            "created_at": CHECKED,
            "adapter_version": ADAPTER_VERSION,
            "snapshot_id": SNAPSHOT_INCHEON if call["seq"] <= 89 else SNAPSHOT_MERGED,
            "complex_id": call["complex_id"],
            "error_text": call["error_text"],
        }
        files[rel] = dumps(env).encode("utf-8")
        index.append({"judgment_seq": call["seq"], "tool": call["tool"], "purpose": call["purpose"], "input_hash": h,
                      "file": rel, "report_ref": call["ref"], "payload": call["payload"]})  # fmt: skip
    meta = {"adapter_version": ADAPTER_VERSION, "recorded_at": "2026-10-07",
            "source": "docs/source/incheon_gimpo_report.md",
            "note": "보고서 부록 A #1~#132 재구성 녹화. adapter_version은 MockAdapter 전용 고정값 'mock-fixture-2026-10-08'이다 — "
                    "실제 JEV 모델은 jev-1.13.0(보고서 §2)이나 payload가 원문 전체가 아닌 재구성이라 실제 어댑터 버전 문자열"
                    "('<코드>+jev-mcp@<서버>+<model>', DECISIONS D6)을 쓰지 않는다. 이 값을 바꾸면 모든 input_hash·파일 이름이 바뀐다"
                    "(contracts/fixtures/README.md 'MockAdapter 규칙').",
            "index": "_index.json = 녹화 132개 목록 [{judgment_seq, tool, purpose, input_hash, file, report_ref, payload}] (judgment_seq 순). "
                     "payload·purpose·adapter_version으로 app.core.protocols.input_hash를 다시 계산하면 input_hash·file 이름과 같다 "
                     "(tests/fixtures_contract/test_judgments.py). prov='jl_<seq>'의 출처표."}  # fmt: skip
    files["_meta.json"] = dumps(meta).encode("utf-8")
    files["_index.json"] = dumps(index).encode("utf-8")
    return index, files


# ---------------------------------------------------------------- 조립


def build() -> dict[str, bytes]:
    """픽스처 디렉터리 기준 상대 경로 → 바이트. expected_scores.json·README.md는 건드리지 않는다."""
    expected = json.loads((FIXTURE / "expected_scores.json").read_text(encoding="utf-8"))
    reg = Registry()
    specs = sorted(COMPLEXES + COMPLEXES_B, key=lambda s: s["id"])
    bundles = [build_bundle(reg, s) for s in specs]
    extra_documents(reg)
    t5 = t5_files(reg)
    docs = reg.finalize_documents()
    refs: dict[str, int] = {}
    for d in docs:
        ref = d.pop("_ref", None)
        if ref:
            refs[ref] = d["id"]
    for src in reg.sources.values():
        if src.doc_id is not None:
            refs[f"@doc:{src.complex_id}:{src.key}"] = src.doc_id
    # 발췌 줄이 없는 출처(예: 경쟁률 페이지에 Fact가 하나도 안 걸린 경우)는 raw_document_id null
    for b in bundles:
        for section in ("competition", "remaining_events", "intake"):
            for row in b[section]:
                r = row.get("raw_document_id")
                if isinstance(r, str) and r not in refs:
                    row["raw_document_id"] = None
    bundles = resolve_refs(bundles, refs)
    t5 = resolve_refs(t5, refs)

    out: dict[str, bytes] = {}
    out["region.json"] = dumps(build_region()).encode("utf-8")
    out["complexes.json"] = dumps(bundles).encode("utf-8")
    out["provenance.json"] = dumps(reg.provenance).encode("utf-8")
    out["snapshots.json"] = dumps([
        {"id": SNAPSHOT_INCHEON, "region_id": REGION_ID, "asof_date": "2026-10-07", "status": "published", "degraded": False,
         "created_at": FETCHED_AT, "published_at": FETCHED_AT, "contradicted_claims": 0, "complex_count": 8},
        {"id": SNAPSHOT_MERGED, "region_id": REGION_ID, "asof_date": "2026-10-08", "status": "published", "degraded": False,
         "created_at": "2026-10-08T00:00:00+09:00", "published_at": "2026-10-08T00:00:00+09:00", "contradicted_claims": 0, "complex_count": 16},
    ]).encode("utf-8")  # fmt: skip
    _, jfiles = build_judgments(expected)
    out.update({f"judgments/{k}": v for k, v in jfiles.items()})

    out["raw/documents.json"] = dumps(docs).encode("utf-8")
    out.update({f"raw/{k}": v for k, v in reg.files.items()})
    out["raw/rtms/t4_metroxi2_84.json"] = dumps(rtms_t4()).encode("utf-8")
    out["raw/rtms/t11_switzen_comparables.json"] = dumps(rtms_t11()).encode("utf-8")
    out["raw/t5_harrington/candidates.json"] = dumps(t5).encode("utf-8")

    # T8: 팝업 이미지 동일/변경 쌍
    out["raw/official_site/elif_popup_2026-10-08_same.png"] = POPUP_ELIF
    out["raw/official_site/elif_popup_2026-10-08_changed.png"] = POPUP_ELIF_CHANGED

    def popup(path: str, data: bytes, fetched: str) -> dict[str, Any]:
        return raw_doc(None, "official_site", ELIF_SITE, path, data, 2, content_type="image/png", image_hash=sha256_hex(data),
                       text_path=None, fetched_at=fetched)  # fmt: skip

    elif_doc = next(d for d in docs if d["path"] == "official_site/elif_popup_2026-10-07.png")
    out["raw/official_site/t8_popup_pairs.json"] = dumps(
        {
            "yesterday": elif_doc,
            "today_same": popup(
                "official_site/elif_popup_2026-10-08_same.png", POPUP_ELIF, "2026-10-08T00:00:00+09:00"
            ),
            "today_changed": popup(
                "official_site/elif_popup_2026-10-08_changed.png",
                POPUP_ELIF_CHANGED,
                "2026-10-08T00:00:00+09:00",
            ),
        }
    ).encode("utf-8")

    # T13: 출처 행을 지운 변형(엘리프 번들 + 출처 일부 삭제)
    elif_bundle = copy.deepcopy(next(b for b in bundles if b["complex"]["id"] == 2))
    removed = [elif_bundle["complex"]["units_total"]["prov"], elif_bundle["types"][0]["max_price_won"]["prov"],
               elif_bundle["types"][0]["balcony_won"]["prov"], elif_bundle["payment_terms"][0]["down_payment_pct"]["prov"]]  # fmt: skip
    used = {r["id"] for r in reg.provenance if r["id"].startswith("fp_2_")}
    out["raw/t13_missing_provenance/complexes.json"] = dumps([elif_bundle]).encode("utf-8")
    out["raw/t13_missing_provenance/provenance.json"] = dumps(
        [r for r in reg.provenance if r["id"] in used and r["id"] not in removed]
    ).encode("utf-8")
    out["raw/t13_missing_provenance/expected.json"] = dumps(
        {
            "case": "T13",
            "removed_prov_ids": removed,
            "fields": [
                "complex.units_total",
                "types[84A].max_price_won",
                "types[84A].balcony_won",
                "payment_terms[0].down_payment_pct",
            ],
            "expected": {
                "dev": "contract_violation 500",
                "prod": "label '확인 불가', reason '출처 누락' + 경고 로그",
            },
        }
    ).encode("utf-8")

    # T3: 사람 확인 입력(스위첸 '가능')
    out["raw/human_check/t3_switzen_possible.json"] = dumps(
        {
            "complex_id": 4,
            "field": "intake_status",
            "value_text": "가능",
            "kind": "phone",
            "checked_at": "2026-10-09",
            "entered_by": "운영자",
            "note": "T3 테스트 입력(RA §9) — 실제 통화 기록 아님. 기대: intake 행(path=human_check) + rejudge 잡 1 → 상황 후보 포함",
        }
    ).encode("utf-8")

    # T6: 복합 주장(#131 contradicted)
    out["raw/claims/t6_composite.json"] = dumps({
        "case": "T6", "expected_min_atomic_claims": 2,
        "claims": [
            {"id": None, "snapshot_id": SNAPSHOT_MERGED, "section": "12-3·12-4", "complex_id": None,
             "text": "고촌센트럴자이 +10%·+20%와 롯데캐슬 +20%만 unlikely, 나머지 전부 uncertain",
             "evidence_text": "jev_noul #118~123 판정 label", "verify_status": "contradicted", "judgment_seq": 131, "parent_claim_id": None, "ordinal": 0},
            {"id": None, "snapshot_id": SNAPSHOT_MERGED, "section": "RA §9 T6", "complex_id": None,
             "text": "3개는 unlikely이고 나머지는 uncertain", "evidence_text": None, "verify_status": None, "judgment_seq": None,
             "parent_claim_id": None, "ordinal": 0},
        ],
    }).encode("utf-8")  # fmt: skip

    # T14: guard 입력 — 전부 가짜 값
    fake_key = "fx-t14-not-a-real-key-7f3a"
    out["raw/guard/t14_payloads.json"] = dumps(
        {
            "case": "T14",
            "env": {"DATA_GO_KR_KEY": fake_key},
            "note": "모든 값은 테스트용 가짜(실제 번호·주소·키 아님). guard는 호출 전 거부하고 judgment_log에 status=blocked 행, 로그엔 input_hash·길이만.",
            "cases": [
                {
                    "kind": "phone",
                    "tool": "screen",
                    "purpose": "screen:t14:phone",
                    "payload": {"text": "엘리프 검단 포레듀 선착순 문의 010-1234-5678"},
                    "expect_status": "blocked",
                },
                {
                    "kind": "email",
                    "tool": "screen",
                    "purpose": "screen:t14:email",
                    "payload": {"text": "계약 서류 회신 test.user@example.com"},
                    "expect_status": "blocked",
                },
                {
                    "kind": "resident_no",
                    "tool": "extract",
                    "purpose": "extract:t14:resident",
                    "payload": {"document": "계약자 900101-1234567"},
                    "expect_status": "blocked",
                },
                {
                    "kind": "env_value",
                    "tool": "verify",
                    "purpose": "verify:t14:env",
                    "payload": {"claims": [{"id": "c1", "text": f"인증키 {fake_key}"}]},
                    "expect_status": "blocked",
                },
            ],
        }
    ).encode("utf-8")

    # T18: 판정기 다운
    out["raw/scenarios/t18_judge_down.json"] = dumps({
        "case": "T18", "adapter": "mock", "raise": "JudgeUnavailable", "when": "모든 판정 메서드 호출(9개 도구)",
        "inputs": {"raw_documents": "raw/documents.json", "complexes": "complexes.json"},
        "expected_snapshot": {"id": 13, "region_id": REGION_ID, "asof_date": "2026-10-09", "status": "building", "degraded": True,
                              "created_at": "2026-10-09T00:00:00+09:00", "published_at": None, "contradicted_claims": None, "complex_count": 16},
        "expected": {"collect_and_normalize": "성공(raw_document·complex 행 생성)", "scores_computed": False, "banner": ["G1", "G7"],
                     "judgment_log": "호출마다 status=error 행(같은 hash 재시도는 UPDATE)", "rejudge_jobs_after_recovery": 1},
    }).encode("utf-8")  # fmt: skip
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="쓰지 않고 비교만(다르면 exit 1)")
    args = ap.parse_args(argv)
    files = build()
    generated_dirs = ("judgments", "raw")
    if args.check:
        diff = [
            rel
            for rel, data in files.items()
            if not (FIXTURE / rel).is_file() or (FIXTURE / rel).read_bytes() != data
        ]
        extra = [p.relative_to(FIXTURE).as_posix() for d in generated_dirs for p in (FIXTURE / d).rglob("*")
                 if p.is_file() and p.relative_to(FIXTURE).as_posix() not in files]  # fmt: skip
        if diff or extra:
            print(
                "픽스처가 생성기와 다르다:", *diff[:20], *(f"(남는 파일) {e}" for e in extra[:20]), sep="\n  "
            )
            return 1
        print(f"ok: {len(files)}개 파일 일치")
        return 0
    for d in generated_dirs:
        for p in sorted((FIXTURE / d).rglob("*"), reverse=True):
            if p.is_file() and p.relative_to(FIXTURE).as_posix() not in files:
                p.unlink()
    for rel, data in files.items():
        target = FIXTURE / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    print(f"wrote {len(files)} files → {FIXTURE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
