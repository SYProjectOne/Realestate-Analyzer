"""재정규화 멱등성 속성 테스트(D23-1)용 재생 매니페스트 — R4 재시험 DB 의 bootstrap 일일 단계 원문 → ``docs.json``.

R4 재시험(D19 로컬 PG) 뒤 같은 원문 전부로 ``tests/scheduler/test_core10_idempotency.py::test_renormalize_is_idempotent[r4d-full]`` 를
로컬에서 돌릴 때 쓴다. **읽기 전용**(SELECT 만, 읽기 전용 트랜잭션). 원문 파일은 복사하지 않고 매니페스트의 ``raw_root`` 가 그 재시험의
RAW_DIR 을 가리킨다.

사용법 (backend/ 에서)::

    REPLAY_DATABASE_URL=… uv run python scripts/replay_manifest.py --raw-root <재시험 RAW_DIR> --out <폴더>
    R4_REPLAY_MANIFEST=<폴더>/docs.json uv run pytest -p no:randomly \
        "tests/scheduler/test_core10_idempotency.py::test_renormalize_is_idempotent[r4d-full]"

``REPLAY_DATABASE_URL`` 은 출력하지 않는다(접속 주소·비밀번호). 지역은 id 가장 작은 것 하나, bootstrap 잡은 그 지역의 첫 ``region.bootstrap``
(done). 일일 단계 = 그 잡 시작부터 첫 실거래(rtms) 원문 전까지의 청약홈·공고문·공식 홈페이지 원문, 원 공고 다시 받기 = 그 구간에서 첫 공고문
뒤·첫 공식 홈페이지 앞에 받은 청약홈 상세. 공식 홈페이지 원문은 단지 id 대신 ``house_no``(그 단지 주택관리번호)로 남긴다(재생 DB 의 단지 id 는
다르다). 지역명 등 값은 DB 에서 그대로 읽는다(코드에 지역명 없음 — AGENTS 규칙 15).
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

COLS = ("id", "source_kind", "url", "fetched_at", "http_status", "sha256", "path", "content_type", "text_path",
        "table_path", "complex_id", "error_text", "image_hash", "meta")  # fmt: skip
DAILY_KINDS = ("applyhome_list", "applyhome_detail", "notice_pdf", "official_site")
_SECRET = re.compile(r"servicekey|authorization|bearer|api_key|token=|x-ncp-apigw", re.I)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--raw-root", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args(argv)
    url = os.environ.get("REPLAY_DATABASE_URL")
    if not url:
        print("REPLAY_DATABASE_URL 없음", file=sys.stderr)
        return 2
    import psycopg

    with psycopg.connect(url.replace("postgresql+psycopg://", "postgresql://")) as conn:
        conn.read_only = True
        region = conn.execute(
            "SELECT id, name, query_text, selections, sido_codes, sigungu_codes, legal_dong_codes, living_areas, "
            "age_premium_coef, supply_ref_pct::text, created_at FROM region ORDER BY id LIMIT 1"
        ).fetchone()
        assert region is not None, "지역 없음"
        rkeys = ("id", "name", "query_text", "selections", "sido_codes", "sigungu_codes", "legal_dong_codes",
                 "living_areas", "age_premium_coef", "supply_ref_pct", "created_at")  # fmt: skip
        reg = dict(zip(rkeys, region, strict=True))
        job = conn.execute(
            "SELECT started_at, finished_at FROM job_run WHERE job_name = 'region.bootstrap' AND status = 'done' "
            "AND (payload->>'region_id')::int = %s ORDER BY id LIMIT 1",
            (reg["id"],),
        ).fetchone()
        assert job is not None, "끝난 region.bootstrap 없음"
        docs = [
            dict(zip(COLS, r, strict=True))
            for r in conn.execute(
                f"SELECT {', '.join(COLS)} FROM raw_document WHERE fetched_at >= %s AND fetched_at <= %s ORDER BY id",
                (job[0], job[1]),
            )
        ]
        houses: dict[int, str | None] = dict(conn.execute("SELECT id, applyhome_id FROM complex").fetchall())
        names = [r[0] for r in conn.execute(
            "SELECT DISTINCT eupmyeondong_name FROM legal_dong WHERE sigungu_code = ANY(%s) AND eupmyeondong_name IS NOT NULL",
            (reg["sigungu_codes"],))]  # fmt: skip
        lcols = ("code", "sido_name", "sigungu_name", "eupmyeondong_name", "ri_name", "full_name", "sigungu_code",
                 "active", "source_date")  # fmt: skip
        legal = [
            dict(zip(lcols, r, strict=True))
            for r in conn.execute(
                f"SELECT {', '.join(lcols)} FROM legal_dong WHERE eupmyeondong_name = ANY(%s) OR sigungu_code = ANY(%s) "
                "OR (eupmyeondong_name IS NULL AND left(code, 2) = ANY(%s)) ORDER BY code",
                (names, reg["sigungu_codes"], reg["sido_codes"]),
            )
        ]
    first_rtms = next((d["id"] for d in docs if d["source_kind"] == "rtms"), None)
    daily = [
        d for d in docs if d["source_kind"] in DAILY_KINDS and (first_rtms is None or d["id"] < first_rtms)
    ]
    first_pdf = next((d["id"] for d in daily if d["source_kind"] == "notice_pdf"), None)
    first_site = next((d["id"] for d in daily if d["source_kind"] == "official_site"), None)
    applyhome: list[dict[str, Any]] = []
    originals: dict[str, list[dict[str, Any]]] = {}
    for d in daily:
        if d["source_kind"] not in ("applyhome_list", "applyhome_detail"):
            continue
        late = first_pdf is not None and d["id"] > first_pdf and (first_site is None or d["id"] < first_site)
        if late and d["source_kind"] == "applyhome_detail":
            m = re.search(r"HOUSE_MANAGE_NO%3A%3AEQ%5D=(\d{10})", d["url"])
            originals.setdefault(m.group(1) if m else "?", []).append(d)
        else:
            applyhome.append(d)
    notice = [d for d in daily if d["source_kind"] == "notice_pdf"]
    site = [d for d in daily if d["source_kind"] == "official_site"]
    for d in site:
        d["house_no"] = houses.get(d["complex_id"])
    for d in daily:
        d["complex_id"] = None
    bad = [d["id"] for d in daily if _SECRET.search(json.dumps(d, ensure_ascii=False, default=str))]
    if bad:
        print(f"키·토큰 모양이 든 원문 행 {len(bad)}개 — 중단", file=sys.stderr)
        return 1
    reg.pop("id")
    groups: dict[str, Any] = {
        "applyhome": applyhome,
        "originals": originals,
        "notice_pdf": notice,
        "official_site": site,
    }
    manifest = {
        "source": f"bootstrap 일일 단계 원문(raw_document id {daily[0]['id'] if daily else '-'}~{daily[-1]['id'] if daily else '-'})",
        "asof": str(job[0])[:10],
        "region": reg,
        "legal_dong": legal,
        "raw_root": str(args.raw_root.resolve()),
        "docs": groups,
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "docs.json").write_text(
        json.dumps(manifest, ensure_ascii=False, default=str, indent=1), encoding="utf-8"
    )
    print(
        {k: (len(v) if isinstance(v, list) else sum(len(x) for x in v.values())) for k, v in groups.items()}
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
