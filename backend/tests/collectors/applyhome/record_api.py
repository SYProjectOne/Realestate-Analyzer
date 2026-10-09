"""청약홈 공식 API 녹화기 — ``fixtures/applyhome_api_2026-10-09.zip`` 생성(사람이 직접 실행, 테스트 아님).

    ENV_FILE=<메인 체크아웃>/.env uv run python -m tests.collectors.applyhome.record_api

- 테스트 지역(conftest ``REGION_DICT``)·기준일(``TODAY``)로 ``ApplyhomeCollector`` 를 실제 키로 한 번 돌린다.
- api.odcloud.kr 응답만 녹화한다. manifest 의 url 에는 serviceKey 가 없고(재생은 serviceKey 를 빼고 맞춘다),
  본문에 키가 들어 있으면 녹화를 멈춘다(키 마스킹 확인).
- 웹(www.applyhome.co.kr) 요청은 같은 날의 웹 녹화(``applyhome_2026-10-09.zip``)로 답한다. 웹 녹화에 없는
  요청만 실제로 보내고 그 응답도 이 zip 에 넣는다.
"""

from __future__ import annotations

import json
import sys
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

import httpx

from app.collectors.applyhome import ApplyhomeCollector
from app.core.db import get_engine, get_sessionmaker, load_metadata, reset_engine
from app.core.http import HttpClient
from app.core.settings import Settings, load_settings, set_settings
from app.models import Region as RegionRow
from app.models import Snapshot as SnapshotRow

from .conftest import FIXTURES, RECORDING, TODAY, make_region, make_snapshot
from .replay import Recording, request_key

OUT = FIXTURES / "applyhome_api_2026-10-09.zip"
SECRET_PARAMS = {"serviceKey"}


def strip_key(url: str) -> str:
    parts = urlsplit(url)
    kept = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k not in SECRET_PARAMS]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(kept), ""))


class Recorder(httpx.BaseTransport):
    def __init__(self, web: Recording, secrets: list[str]) -> None:
        self.live = httpx.HTTPTransport(retries=0)
        self.web = web
        self.secrets = [s for s in secrets if s]
        self.entries: list[dict[str, object]] = []
        self.files: dict[str, bytes] = {}

    def _record(self, request: httpx.Request, response: httpx.Response, prefix: str) -> None:
        body = response.read()
        for s in self.secrets:
            if s.encode() in body or s in str(response.headers):
                raise SystemExit("응답에 키가 들어 있다 — 녹화 중단")
        name = f"{prefix}_{len(self.entries):04d}.{'json' if prefix == 'api' else 'html'}"
        form = None
        if request.method == "POST":
            form = dict(parse_qsl(request.content.decode("utf-8"), keep_blank_values=True))
        self.entries.append(
            {
                "method": request.method,
                "url": strip_key(str(request.url)),
                "form": form,
                "status": response.status_code,
                "content_type": response.headers.get("content-type", ""),
                "file": name,
            }
        )
        self.files[name] = body

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if request.url.path == "/robots.txt":
            return httpx.Response(404, text="not found")
        if host == "api.odcloud.kr":
            response = self.live.handle_request(request)
            response.read()
            self._record(request, response, "api")
            return httpx.Response(response.status_code, content=response.content, headers=response.headers)
        form = None
        if request.method == "POST":
            form = dict(parse_qsl(request.content.decode("utf-8"), keep_blank_values=True))
        entry = self.web.entries.get(request_key(request.method, str(request.url), form))
        if entry is not None:
            return httpx.Response(
                entry.status, content=self.web.body(entry), headers={"content-type": entry.content_type}
            )
        response = self.live.handle_request(request)
        response.read()
        self._record(request, response, "web")
        return httpx.Response(response.status_code, content=response.content, headers=response.headers)


def main() -> int:
    live = load_settings()
    key = live.data_go_kr_key.get_secret_value() if live.data_go_kr_key else ""
    if not key:
        print("DATA_GO_KR_KEY 없음 — ENV_FILE 로 .env 경로를 준다", file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory() as tmp:
        settings = Settings(
            _env_file=None,
            database_url=f"sqlite:///{Path(tmp, 'rec.db').as_posix()}",
            raw_dir=Path(tmp, "raw"),
            judge_adapter="mock",
        )
        set_settings(settings)
        try:
            engine = get_engine(settings)
            md = load_metadata()
            assert md is not None
            md.create_all(engine)
            region, snapshot = make_region(), make_snapshot()
            session = get_sessionmaker()()
            session.add(
                RegionRow(
                    id=region.id,
                    name=region.name,
                    query_text=region.query_text,
                    selections=[s.model_dump() for s in region.selections],
                    sido_codes=region.sido_codes,
                    sigungu_codes=region.sigungu_codes,
                    legal_dong_codes=region.legal_dong_codes,
                    living_areas=[],
                    age_premium_coef=region.age_premium_coef.model_dump(),
                    supply_ref_pct=region.supply_ref_pct,
                    applyhome_query=region.applyhome_query,
                    status=region.status,
                    created_at=region.created_at,
                )
            )
            session.add(
                SnapshotRow(
                    id=1,
                    region_id=1,
                    asof_date=snapshot.asof_date,
                    status="building",
                    created_at=snapshot.created_at,
                )
            )
            session.flush()
            rec = Recorder(Recording.load(RECORDING), [key, unquote(key)])
            with HttpClient(transport=rec, max_retries=1, jitter=0.0) as http:
                c = ApplyhomeCollector(http=http, session=session, today=lambda: TODAY, service_key=key)
                docs = c.fetch(region, snapshot, None)
            session.rollback()
            session.close()
        finally:
            set_settings(None)
            reset_engine()
    with zipfile.ZipFile(OUT, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps({"entries": rec.entries}, ensure_ascii=False, indent=1))
        for name, body in rec.files.items():
            z.writestr(name, body)
    statuses: dict[int, int] = {}
    for e in rec.entries:
        st = int(str(e["status"]))
        statuses[st] = statuses.get(st, 0) + 1
    print(f"paths={c.paths} docs={len(docs)} entries={len(rec.entries)} statuses={statuses} -> {OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
