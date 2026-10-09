"""합성 단지 생성기 (WP9, RA §9 T16 성능: /complexes 첫 페이지 1초 이내, G2 가상화 스크롤).

ComplexBundle(contracts/schemas/complex.json#/$defs/ComplexBundle) n개를 결정적으로(같은 seed = 같은 결과) 만든다.
- 합성 단지는 이름 '합성 단지 0001' · fixture_key 'synth_0001'로 구별된다. 실제 단지·가격과 무관하다.
- 모든 수치는 Fact이고 라벨은 '추정'(reason '합성(T16)'), prov는 'fp_synth_<id>_<n>'(provenance 행 없음 — 성능 전용).
- id는 100001부터(회귀 픽스처 1~16과 겹치지 않음), applyhome_id는 '9'로 시작하는 10자리.
- 지역·생활권·법정동은 회귀 픽스처 region(id 1, la_1~la_4)의 것을 쓴다.

사용: python contracts/fixtures/tools/synth.py --n 1000 --seed 16 --out synth_1000.json
(성능 테스트가 메모리에서 바로 쓰려면 ``generate(1000)``. 생성물은 커밋하지 않는다.)
"""

# ruff: noqa: E501  (데이터 표 한 줄 유지)
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any

LIVING_AREAS = [
    ("la_1", "연수구", "2818510600", "인천광역시 연수구 송도동"),
    ("la_2", "서구(검단)", "2826011300", "인천광역시 검단구 마전동"),
    ("la_3", "계양구", "2824511000", "인천광역시 계양구 동양동"),
    ("la_4", "김포시", "4157010700", "경기도 김포시 풍무동"),
]
REASON = "합성(T16)"
CHECKED = "2026-10-08"
FIRST_ID = 100001


class _Facts:
    def __init__(self, cid: int) -> None:
        self.cid = cid
        self.n = 0

    def __call__(self, v: Any, unit: str) -> dict[str, Any]:
        self.n += 1
        return {
            "v": v,
            "label": "추정",
            "reason": REASON,
            "prov": f"fp_synth_{self.cid}_{self.n}",
            "checked_at": CHECKED,
            "unit": unit,
        }


def _date(rng: random.Random, year_from: int, year_to: int) -> str:
    return f"{rng.randint(year_from, year_to)}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"


def _bundle(i: int, rng: random.Random) -> dict[str, Any]:
    cid = FIRST_ID + i
    fact = _Facts(cid)
    la_id, la_name, code, addr = LIVING_AREAS[i % len(LIVING_AREAS)]
    units = rng.randint(150, 3000)
    general = rng.randint(units // 3, units - 50)
    notice = _date(rng, 2024, 2026)
    winner = notice[:8] + f"{min(int(notice[8:]) + rng.randint(5, 20), 28):02d}"
    move_in = f"{rng.randint(2027, 2031)}-{rng.randint(1, 12):02d}"
    public = rng.random() < 0.5
    resale = 36 if public else 6
    base_price = rng.randrange(450_000_000, 1_300_000_000, 1_000_000)
    types: list[dict[str, Any]] = []
    for code_t in ["59A", "74A", "84A", "84B"][: rng.randint(1, 4)]:
        area = float(code_t[:2])
        max_price = int(base_price * area / 84 // 100_000 * 100_000)
        types.append({
            "id": None, "complex_id": cid, "type_code": code_t, "area_m2": fact(round(area + rng.random(), 2), "m2"),
            "units": fact(rng.randint(10, max(11, units // 3)), "units"), "max_price_won": fact(max_price, "won"),
            "floor_sample_price_won": fact(int(max_price * 0.95 // 100_000 * 100_000), "won"), "floor_sample_text": "1층",
            "balcony_won": fact(rng.randrange(0, 30_000_000, 10_000), "won"), "options_required_won": fact(0, "won"),
            "options_text": None, "is_basis": False,
        })  # fmt: skip
    basis = min(types, key=lambda t: (abs(t["area_m2"]["v"] - 84), t["type_code"]))
    basis["is_basis"] = True
    down = rng.choice([5, 10])
    complex_ = {
        "id": cid, "region_id": 1, "applyhome_id": f"9{cid:09d}", "name": f"합성 단지 {i + 1:04d}", "former_names": [],
        "address": f"{addr} 합성 {i + 1}번지", "legal_dong_code": code, "living_area": la_id, "living_area_name": la_name,
        "official_site_url": None, "developer": "합성 시행사", "trustee": None, "builder": "합성 건설사",
        "housing_type": fact("민영", "text"), "land_type": fact("공공택지" if public else "민간택지", "text"),
        "price_cap": fact("적용" if public else "미적용", "text"), "regulated": fact("비규제", "text"),
        "units_total": fact(units, "units"), "units_general": fact(general, "units"), "units_special": fact(units - general, "units"),
        "officetel_units": fact(0, "units"), "notice_date": fact(notice, "date"), "apply_dates": [],
        "winner_date": fact(winner, "date"), "contract_dates": [], "move_in_ym": fact(move_in, "ym"),
        "resale_months": fact(resale, "months"), "resale_end": None,
        "resale_release_on_registration": fact("등기 시 해제" if public else "해당 없음", "text"),
        "residency_months": fact(0, "months"), "rewin_restriction_years": fact(10 if public else 0, "years"),
        "inclusion_class": "private_sale_apt", "inclusion_decision": "auto", "inclusion_prob": fact(round(rng.uniform(0.86, 1.0), 2), "prob"),
        "track": rng.choice(["A", "B"]),
    }  # fmt: skip
    payment = [{
        "id": None, "complex_id": cid, "notice_no": complex_["applyhome_id"], "notice_kind": "본청약",
        "effective_from": fact(notice, "date"), "down_payment_pct": fact(down, "pct"),
        "down_payment_first_won": fact(10_000_000, "won"), "interim_pct": fact(60, "pct"), "interim_terms_text": "중도금 60% 이자후불",
        "balance_pct": fact(100 - down - 60, "pct"), "interim_schedule": [], "is_current": True, "change_vs_first": None,
    }]  # fmt: skip
    intake = [{
        "id": None, "complex_id": cid, "snapshot_id": None, "status": rng.choice(["가능", "미정", "불가"]), "path": "official_popup",
        "evidence_url": None, "screenshot_path": None, "raw_document_id": None, "checked_at": CHECKED, "http_status": 200,
        "reason": None, "note": None, "entered_by": None,
    }]  # fmt: skip
    for row in intake:
        if row["status"] == "불가":
            row["reason"] = "마감"
    return {"fixture_key": f"synth_{i + 1:04d}", "complex": complex_, "types": types, "payment_terms": payment,
            "competition": [], "remaining_events": [], "intake": intake}  # fmt: skip


def generate(n: int = 1000, seed: int = 16) -> list[dict[str, Any]]:
    """합성 ComplexBundle n개(같은 n·seed = 같은 결과)."""
    rng = random.Random(seed)
    return [_bundle(i, rng) for i in range(n)]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=16)
    ap.add_argument("--out", type=Path, help="출력 JSON 경로(생략하면 표준 출력)")
    args = ap.parse_args(argv)
    text = json.dumps(generate(args.n, args.seed), ensure_ascii=False, indent=1) + "\n"
    if args.out:
        args.out.write_text(text, encoding="utf-8", newline="\n")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
