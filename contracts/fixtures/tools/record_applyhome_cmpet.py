"""청약홈 경쟁률 API(data.go.kr 15098905, ApplyhomeInfoCmpetRtSvc) 실응답 녹화기 — 사람이 직접 실행(테스트 아님).

    ENV_FILE=<메인 체크아웃>/.env uv run python ../contracts/fixtures/tools/record_applyhome_cmpet.py   # backend/ 에서

인천·김포 회귀 픽스처 단지의 공고 몇 건을 APT·무순위(Remndr)·임의공급(OPT) 경쟁률 3종으로 한 번씩 조회해
``backend/tests/collectors/applyhome/fixtures/applyhome_cmpet_2026-10-09/`` 에 그대로 저장한다.

- 호출은 수집기와 같은 ``app.collectors.applyhome.api.ApplyhomeApi``(키는 쿼리로만, 돌려주는 url 은 키 없음).
- manifest 의 url 에는 serviceKey 가 없다. 본문·헤더에 키(인코딩·디코딩 둘 다)가 있으면 저장하지 않고 멈춘다.
- 키 값은 출력하지 않는다(길이도). 실패(401·0건)도 녹화한다 — 실패도 데이터(AGENTS 7).
"""

# ruff: noqa: E501
from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import unquote

TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parents[2]
BACKEND = REPO / "backend"
OUT = BACKEND / "tests" / "collectors" / "applyhome" / "fixtures" / "applyhome_cmpet_2026-10-09"
sys.path.insert(0, str(BACKEND))

# (kind, 주택관리번호, 공고번호, 픽스처 단지) — 보고서·complexes.json 의 공고
TARGETS: list[tuple[str, str, str, str]] = [
    ("apt", "2026000367", "2026000367", "9 한강 푸르지오 리버프론트(김포, 본청약 2026-07)"),
    ("apt", "2025000582", "2025000582", "3 송도 한내들 센트럴리버(인천, 본청약 2025-12)"),
    ("apt", "2026000164", "2026000164", "1 더샵 송도그란테르 G5-1(인천, 본청약 2026-05)"),
    ("apt", "2025000222", "2025000222", "4 오퍼스 한강 스위첸(김포, 본청약 2025-06)"),
    ("remndr", "2026910203", "2026910203", "1 더샵 송도그란테르 무순위 1차(2026-07-30)"),
    ("remndr", "2026910216", "2026910216", "6 더샵 검단레이크파크 AB23 무순위(2026-08)"),
    ("remndr", "2026910242", "2026910242", "12 더샵 송도마리나베이 무순위 3회차(2026-09-10)"),
    ("opt", "2026940088", "2026940088", "3 송도 한내들 센트럴리버 임의공급(2026-05-06)"),
    ("opt", "2026940116", "2026940116", "7 김포 칸타빌 에디션 임의공급 2차(2026-06)"),
    ("opt", "2026940173", "2026940173", "2 엘리프 검단 포레듀 임의공급 3차(2026-08)"),
]


def main() -> int:
    from app.collectors.applyhome import api
    from app.core.http import HttpClient
    from app.core.settings import load_settings

    s = load_settings()
    key = s.data_go_kr_key.get_secret_value() if s.data_go_kr_key else ""
    if not key:
        sys.stdout.write("DATA_GO_KR_KEY 없음 — ENV_FILE 로 메인 체크아웃 .env 를 준다\n")
        return 2
    secrets = {key, unquote(key)}
    OUT.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, object]] = []
    with HttpClient(max_retries=1) as http:
        client = api.ApplyhomeApi(http, key)
        for kind, house, pblanc, label in TARGETS:
            path = api.ENDPOINTS[kind].competition  # type: ignore[index]
            r = client.get(path, api.item_params(house, pblanc))
            body = r.content or b""
            text_headers = json.dumps(dict(r.headers or {}), ensure_ascii=False)
            if any(sec and (sec.encode() in body or sec in text_headers or sec in r.url) for sec in secrets):
                sys.stdout.write("응답·주소에 키가 들어 있다 — 녹화 중단\n")
                return 3
            name = f"{path.rsplit('/', 1)[1]}_{house}.json"
            (OUT / name).write_bytes(body)
            page = api.parse_page(r)
            manifest.append({"kind": kind, "house_manage_no": house, "pblanc_no": pblanc, "complex": label,
                             "url": r.url, "status": r.status, "content_type": (r.headers or {}).get("content-type", ""),
                             "rows": len(page.rows), "error": page.error, "file": name})  # fmt: skip
            sys.stdout.write(f"{kind:6} {house} HTTP {r.status} rows={len(page.rows)} {page.error or ''}\n")
    meta = {
        "recorded_at": "2026-10-09",
        "service": "data.go.kr 15098905 ApplyhomeInfoCmpetRtSvc/v1 (APT·Remndr·OPT 경쟁률) — 사람 활용신청 승인 2026-10-09",
        "recorder": "contracts/fixtures/tools/record_applyhome_cmpet.py",
        "note": "실응답 그대로(serviceKey 는 url 에서 빠져 있고 본문에 없음을 확인). synthetic_ 경쟁률 픽스처를 대체한다.",
        "entries": manifest,
    }
    (OUT / "manifest.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
