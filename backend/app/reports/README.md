# app/reports

- **주인**: WP8
- **읽기 허용**: — (다른 WP 는 읽지 않는다)
- 쓰기 금지 이유(RA §2): —

## 범위 (RA §2·§5, DECISIONS D4)

보고서 = **HTML + PDF** (md·docx·32KB 분할 없음).
`templates/*.html.j2`(첫 장 + §1~§11 + 지역 추가 장 + 부록 A 판정 로그 · B 참고자료 · C 용어 풀이 · D 전체 표), `render.py`(자립 HTML: CSS·ECharts 인라인),
`pdf.py`(Playwright chromium `page.pdf()`), `diff.py`, `cli.py`(`python -m app.reports.cli --snapshot <id> --format pdf`).

- 출력 디렉터리: `app.core.paths.report_dir()` (`REPORT_DIR`).
- 점수는 `app.analysis` 결과를 읽기만 한다(ADR-11).
- Docker worker 이미지에 한글 글꼴(`fonts-noto-cjk`)과 chromium 이 들어 있다(`infra/Dockerfile.worker`).

## 모듈

| 모듈 | 내용 |
| --- | --- |
| `data.py` | `load_report(session, snapshot_id, *, scenario_id=None, compare_snapshot_id=None) -> ReportData`. DB → 뷰 모델, 모든 수치 `Fact`(fp_/sc_/st_/jl_). 값이 있는데 출처 행 없음 = ENV=dev `ReportProvenanceMissing` / ENV=prod 경고 로그 + '확인 불가(출처 누락)'(API `FactMaker.missing` 과 같은 규칙) |
| `policy.py` | **판정 범위·현재 구매가 = 공용 함수 호출만**(규칙 중복 없음) — `judge_scope(...)` = `analysis.scope.judge_scope`(→ `ScopeResult` 범위·사유), `current_price(types, payments)` = `analysis.price_view.current_price`, `current_terms`·`pick_intake`(공용 정렬), `complex_scope(cx, types, payments, intakes)`, `shows_ladder(scope)`(사다리 참여 = '판정 대상'만), `scope_note(result)`('판정 범위: <문구> — <사유>') |
| `render.py` | `render_html(data, *, diff=None, echarts_js=None) -> RenderResult` — Jinja2 단일 자립 HTML(CSS·ECharts·option JSON 인라인) |
| `charts.py` | C1 사다리·C4 입주 물량·C6 점수 분해·C7 decide option(프론트 `buildOption.ts` 규칙), 차트마다 같은 데이터 표. 제목 '지표 · 기간 · 단위', 범례 단위(`legend.formatter`), `source`('자료: … · 라벨 … · 확인일 …')·`note`(그림 읽는 법) |
| `cover.py` | 첫 장 `build_cover(data, diff, revision=…)`(접수 가능·상위 3곳·상황별 선택·판정 범위·비교 건수 — 기존 값과 개수만), `TermState`(용어 첫 등장 괄호 풀이), `delta_mark`·`diff_mark`·`rank_move`(▲▼ + 글자) |
| `glossary.py` | 용어 원본(05-persona §7 + 30-proposal §7-3 고칠 것, key = 프론트 `ko.json glossary.items`) · `forbidden_hits`(30-proposal §1 금지어, '보장 아님'만 허용) |
| `sections.py` | 장 제목(`SECTION_TITLES` 11개 — T15 기준, `ORIGINAL_TITLES` RA 원 이름), `EXTRA_TITLE`, 부록 C·D 제목, 본문·부록 묶음(`BODY_TITLES`·`APPENDIX_TITLES`) |
| `pdf.py` | `html_to_pdf(html, pdf)` — chromium, file: 외 네트워크 차단, `window.__reportReady` 대기. 한 번 인쇄해 `count_pages`(쪽 첫 글 = 장 제목으로 본문·부록 쪽 수)를 센 뒤 첫 장 `data-pages` 칸을 채우고 다시 인쇄 |
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
  `thresholds` 를 도구별로 모은다(D6). 같은 키의 값이 호출마다 다르면(JEV 업데이트) 호출 순으로 모두 `a / b`.
- 판정 범위(§3 열·§6 비고): 제외 · 미해결(classify review·manual_review·미분류) · 보류(분양가 미공개) ·
  참고 후보(표시 접수 상태 확인 불가·불가·없음) · 판정 대상(가능·미정). 표시 접수 상태 = 공용 `pick_intake`
  (human_check > official_popup > headless_shot, 같은 경로면 확인 날짜 → id; unofficial_ref 미사용).
- **스냅샷 저장값 기준(D10-1)**: 판정 범위·순위·종합·성분 = 그 스냅샷 보고서 시나리오 score_run 의 저장값
  (`score_total.judge_scope` 등). 현재 사실로 공용 함수 계산한 범위(`ComplexView.current_scope`)가 다르면 '재판정 필요'
  배지(§3·§6-4·§7·§8-1)만 — 한 행에 섞지 않는다. 저장값이 없는 단지(점수 행 없음)만 현재 사실 범위(`scope_source`).
  §12 diff 의 사다리 참여도 각 스냅샷 저장 범위 기준.
- 사다리 참여 규칙(D9-1, API `views.load_bundles` 와 같음): 사다리 행·p10 은 '판정 대상' 단지만 표시·집계한다.
  참고·보류·미해결·제외 단지에 남은 사다리 행(이전 범위 판정·이월)은 `ReportData.ladders`·`ladder_other`·부록 A
  반영 위치·§12 diff 에 쓰지 않고, C1·§6-1·§7·§8-1 의 확률 자리에 '판정 범위: <문구> — <사유>'(`ladder_scoped_out`).
- 상황별 decide(§8-2): 상황 요약 표(선택·확률·confidence·차순위) + 상황마다 C7(보고서 시나리오 `c07`, 그 밖
  `c07_<코드>`). 가상 후보 '모집공고 대기'(wait_new, 계약 .5 — 내장 A)는 '가상 후보' 배지·막대 라벨, 근거 =
  그 decide 입력(judgment_log.input_json.evidence)의 `[wait_new]` 블록 그대로(없으면 '근거 블록 기록 없음').
- 벤치마크(§5-1, N-M3·N-M4): 지역 생활권마다 묶음(`benchmark_areas`). 행이 없으면 '벤치마크 없음(사유)' — 사유 =
  그 생활권 단지의 저장된 벤치마크 성분 산출식, 없으면 기본 문구. 지역 전체 대체 행(`benchmark.substitute`, 계약 .7)은
  '대체' 배지를 달고 지역 건수·최근 3년 사례 집계에 다시 세지 않는다.
- 캘린더(§8-4, 기준일~+3개월): apply_dates `[{kind,date}]`·`[{kind,start,end}]`, contract_dates `[{from,to}]`,
  interim_schedule `[{seq,due_date}]`(문자열 또는 Fact 모양), remaining_event.apply_dates + 체크리스트 기한.
  문자열 날짜의 출처 = 그 필드의 출처 행(complex.apply_dates 등).
- C1·C7 막대 라벨 = 표와 같은 문자열('0.35 추정[ · verdict/동률]', 소수 2자리 ROUND_HALF_UP), 미해결은 '미해결'.
  C6 미판정 성분 = 길이 0 + '미판정' 라벨.
- §8 숫자(종합 점수)는 `score_total.total` 원값의 소수 2자리 ROUND_HALF_UP, `data-prov="st_<실행>_<단지>"`(성분은 `sc_<실행>_<단지>_<성분>` — API 출처 서랍 id 와 같다, 계약 .13 m6. .13 이전 저장본의 `st_<행>`·`sc_<행>` 은 0014 가 바꾼다 — 계약 .14 m5).
- §12 지역 추가·변경 장은 `--compare` 가 있을 때만(후보 변화·rerank 재실행·순위 변화 + diff 표).
- ECharts 번들: 인자 → Settings `report_echarts_js`(환경변수 `REPORT_ECHARTS_JS`, worker 이미지는 `/opt/echarts/echarts.min.js`) → `frontend/node_modules/echarts/dist/echarts.min.js`.
  없으면 차트 자리에 문구 + 같은 데이터 표(`charts_inlined=False`, CLI 경고).

- **첫 장·본문/부록(R9-REPORT, D28-4, 30-proposal §11-2)**: 첫 장 = 메타 상자(지역·기준일·리비전·발행·시나리오·비교 기준일·
  본문/부록 쪽수·자료 출처 수와 확인일·판정기 버전·계약 버전·고지) + 요약 5줄(기존 값만) + 읽는 법 3줄 + 표기 규칙. 장 제목은 쉬운 말
  + 원 용어 괄호('§8 종합 추천' → '§8 종합 정리(판정기 결과)'). 본문 §1-2·§4 는 4열 요약 표, §6-3·6-4 는 C6 그림·TOP 5 만 —
  원래 표는 부록 D(값·라벨·출처 id 그대로, `tests/reports/golden/r9_fact_cells_before.json` 상위 집합). HTML판 쪽수 칸은 '—'(PDF판만 숫자).

## 테스트

`uv run pytest tests/reports` — 픽스처 적재는 `app.api.devseed.seed` 하나(스냅샷 11·12 점수·decide·접수 상태·claim
포함). `tests/reports/_seed.py` 는 시험이 쓰는 id 수집과 contradicted 주장 추가 함수만 둔다. 판정기 호출 없음.
리뷰 항목별 테스트는 `test_r3_fix.py`, 판정 범위 정합(공용 함수·참여 규칙·wait_new)은 `test_scope_participation.py`,
첫 장·부록·용어·증감 표식(R9-REPORT)은 `test_r9_report.py`.

## 규칙

- 이 디렉터리와 `backend/tests/reports/` 만 주인이 쓴다. 다른 WP는 읽기만 하고, 고칠 것은 요청으로 남긴다(AGENTS 규칙 1).
- 공통 도구는 `app.core` 를 쓴다(`app/core/README.md`). 모델·계약은 `app/models`, `contracts/` (WP0) — 읽기 전용.
- 지역명 하드코딩 금지(규칙 15).
