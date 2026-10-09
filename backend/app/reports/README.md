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

## 규칙

- 이 디렉터리와 `backend/tests/reports/` 만 주인이 쓴다. 다른 WP는 읽기만 하고, 고칠 것은 요청으로 남긴다(AGENTS 규칙 1).
- 공통 도구는 `app.core` 를 쓴다(`app/core/README.md`). 모델·계약은 `app/models`, `contracts/` (WP0) — 읽기 전용.
- 지역명 하드코딩 금지(규칙 15).
