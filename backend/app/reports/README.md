# app/reports

- **주인**: WP8
- **읽기 허용**: — (다른 WP 는 읽지 않는다)
- 쓰기 금지 이유(RA §2): —

## 범위 (RA §2·§5, DECISIONS D4)

보고서 = **HTML + PDF** (md·docx·32KB 분할 없음).
`templates/*.html.j2`(§1~§11 + 지역 추가 장 + 부록 A 판정 로그 · B 참고자료), `render.py`(자립 HTML: CSS·ECharts 인라인),
`pdf.py`(Playwright chromium `page.pdf()`), `diff.py`, `cli.py`(`python -m app.reports.cli --snapshot <id> --format pdf`).

- 출력 디렉터리: `app.core.paths.report_dir()` (`REPORT_DIR`).
- 점수는 `app.analysis` 결과를 읽기만 한다(ADR-11).
- Docker worker 이미지에 한글 글꼴(`fonts-noto-cjk`)과 chromium 이 들어 있다(`infra/Dockerfile.worker`).

## 모듈

| 모듈 | 내용 |
| --- | --- |
| `data.py` | `load_report(session, snapshot_id, *, scenario_id=None, compare_snapshot_id=None) -> ReportData`. DB → 뷰 모델, 모든 수치 `Fact`(fp_/sc_/st_/jl_). 출처 행 없는 수치 = '확인 불가(출처 누락)' |
| `render.py` | `render_html(data, *, diff=None, echarts_js=None) -> RenderResult` — Jinja2 단일 자립 HTML(CSS·ECharts·option JSON 인라인) |
| `charts.py` | C1 사다리·C4 입주 물량·C6 점수 분해·C7 decide option(프론트 `buildOption.ts` 규칙), 차트마다 같은 데이터 표 |
| `pdf.py` | `html_to_pdf(html, pdf)` — chromium, file: 외 네트워크 차단, `window.__reportReady` 대기 |
| `diff.py` | `diff_snapshots(session, base_id, snapshot_id, *, scenario_code="base") -> SnapshotDiff` |
| `export.py` | `generate(session, snapshot_id, "html"\|"pdf", *, compare_snapshot_id, scenario_id, out_dir) -> GeneratedReport`, `ReportExporter`(Exporter Protocol) |
| `job.py` | `report` 잡 처리 — 아래 '잡 규약' |
| `cli.py` | `python -m app.reports.cli --snapshot 12 --format pdf [--compare 11] [--scenario 2] [--out DIR]` (종료 0 성공 · 2 없음 · 3 거부) |

파일 이름: `report_<asof>[_vs_<비교 asof>][_<시나리오 코드>].<html|pdf>` (계약 Report 예시와 같음).

## 잡 규약 (WP7 runner → WP8)

```text
from app.reports.job import run_report_job   # 또는 handle(job_run, session)
stats = run_report_job(job.payload, session=session)
# payload = ReportRequest{snapshot_id, format, compare_snapshot_id?, scenario_id?}
# 성공: job_run.stats = stats  {path, filename, format, size_bytes, sha256, snapshot_id, compare_snapshot_id,
#                               scenario_id, scenario_code, charts, charts_inlined, blocked_reason: None}
```

| 예외 | runner 처리 |
| --- | --- |
| `app.reports.errors.ReportBlocked` | status=failed, error_text=`blocked: {exc.reason}`, stats=`{"blocked_reason": exc.reason}` (API Report.blocked_reason · 409) |
| `ReportNotFound` | failed, error_text=`not_found: {exc.reason}` |
| `ValueError`(pydantic ValidationError 포함) | failed — payload 형식 오류 |

동기 함수다(Playwright sync API) — 실행 중인 asyncio 루프 안에서 부르지 않는다(worker 스레드).

## 정한 것

- **남은 contradicted** = `verify_status='contradicted'` 이고 분할 자식 주장(`parent_claim_id`)이 없는 claim. 복합 주장을 원자
  주장으로 나눠 다시 검증했으면(T6) 자식 결과를 쓴다. 하나라도 남으면 파일을 만들기 전에 `ReportBlocked`.
- 스냅샷의 단지 범위 = 그 스냅샷 파생 테이블(score_total·intake_status·ladder·judgment_log)에 나온 단지. 없으면 지역 전체.
- 부록 A = 같은 지역에서 기준일이 이 스냅샷 이하인 스냅샷들의 judgment_log 전부(누계). 임계값은 `output_json` 안의
  `thresholds` 를 도구별로 모은다(D6).
- §8 숫자(종합 점수)는 `score_total.total` 원값의 소수 2자리 ROUND_HALF_UP, `data-prov="st_<id>"`.
- §12 지역 추가·변경 장은 `--compare` 가 있을 때만(후보 변화·rerank 재실행·순위 변화 + diff 표).
- ECharts 번들: 인자 → 환경변수 `REPORT_ECHARTS_JS` → `frontend/node_modules/echarts/dist/echarts.min.js`.
  없으면 차트 자리에 문구 + 같은 데이터 표(`charts_inlined=False`, CLI 경고).

## 테스트

`uv run pytest tests/reports` — WP5 devseed 가 없어서 `tests/reports/_seed.py` 가 픽스처 스냅샷 11·12를 DB에 적재한다
(파생 테이블은 녹화 봉투 + `app.analysis` (a)단계 점수로 재구성, 판정기 호출 없음).

## 규칙

- 이 디렉터리와 `backend/tests/reports/` 만 주인이 쓴다. 다른 WP는 읽기만 하고, 고칠 것은 요청으로 남긴다(AGENTS 규칙 1).
- 공통 도구는 `app.core` 를 쓴다(`app/core/README.md`). 모델·계약은 `app/models`, `contracts/` (WP0) — 읽기 전용.
- 지역명 하드코딩 금지(규칙 15).
