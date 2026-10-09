# contracts/ — 계약 (WP0 소유, 나머지는 읽기 전용)

프론트↔백엔드(REST), 백엔드 모듈 사이(Python Protocol), 프로세스 사이(job_run.payload)의 접점을 파일로 고정한다
(RA §4). 현재 버전은 [`CHANGELOG.md`](CHANGELOG.md)의 맨 위 항목 하나다.

## 구성

| 경로 | 원본/생성 | 내용 |
| --- | --- | --- |
| `schemas/**/*.json` | **원본** | JSON Schema 2020-12. 파일 하나 = 타입 하나(`title`), 보조 타입은 `$defs`. `$id`는 파일 이름(상대 URI) |
| `openapi.yaml` | **원본** | OpenAPI 3.1. `components.schemas`는 `./schemas/x.json`을 `$ref`, 예시는 `./examples/x.json`을 `$ref` |
| `examples/*.json` | **원본** | OpenAPI Example Object(`summary`, `value`). 인천·김포 보고서 기반 응답 예시 — 프론트 MSW 데이터 |
| `openapi.bundled.yaml` | 생성 | 외부 `$ref` 없는 자립 번들. 프론트 타입(`openapi-typescript`)·MSW는 이것 |
| `../backend/app/core/contracts_gen.py` | 생성 | 번들 components 전부의 pydantic v2 모델 |
| `migrations/` | **원본** | Alembic. `versions/0001_init.py`가 DDL 원본, `../backend/app/models`가 그 거울 |
| `fixtures/` | WP9 | 회귀 픽스처([`fixtures/README.md`](fixtures/README.md)). `expected_scores.json` 시드만 WP0-A |

## 생성 명령 (backend/ 에서)

```bash
uv run python scripts/gen_contracts.py          # openapi.bundled.yaml + app/core/contracts_gen.py 갱신
uv run python scripts/gen_contracts.py --check  # 생성물이 원본과 다르면 exit 1 (테스트가 강제)
uv run alembic upgrade head                     # DATABASE_URL 우선, 기본 sqlite:///./dev.db
uv run pytest tests/contracts                    # 계약 테스트(Postgres는 pgserver 임베디드로 자동)
```

프론트(frontend/): `npm run gen:api`가 `contracts/openapi.bundled.yaml`에서 `src/api/schema.d.ts`를 만든다.

## 변경 절차 (오케스트레이터만)

1. WP 에이전트는 계약을 고치지 않는다. 필요하면 완료 보고의 "계약 변경 요청"(대상 파일 · 변경 내용 · 이유 · 영향 WP)으로 올린다.
2. 오케스트레이터는 하루 한 번 모아 판단한다. 승인하면:
   - 원본(`schemas/`, `openapi.yaml`, `examples/`)을 고친다. 필드 삭제·의미 변경은 새 버전에서만.
   - DB가 바뀌면 `migrations/versions/`에 **새 리비전**을 추가하고(기존 파일은 고치지 않음) `backend/app/models`를 같이 고친다.
   - `uv run python scripts/gen_contracts.py`로 생성물을 다시 만든다.
   - `CHANGELOG.md` 맨 위에 새 버전(`YYYY-MM-DD.k`)과 변경점·영향 WP를 적고, `info.version`과
     `app.core.protocols.CONTRACT_VERSION`을 올린다.
   - `uv run pytest tests/contracts`가 green이어야 한다(모든 예시가 스키마를 통과, 재생성 diff 0, autogenerate diff 0).
3. 영향받는 WP 에이전트에게 변경점만 다시 전달한다.

## 규칙 요약

- 수치·날짜는 `Fact {v, label, prov, checked_at}`로만 나간다(`schemas/fact.json` 설명이 표시 규칙의 원본).
- 라벨 5종: 확인됨·추정·비공식·재가공·확인 불가(사유는 `reason`). '사람 확인'은 라벨이 아니라 `human=true` / `path=human_check`.
- 판정 봉투 `JudgmentEnvelope`의 status가 review·escaped·blocked·error면 점수·추천에 쓰지 않는다(WP4가 거른다).
- 지역명은 코드에 없다. 지역은 `region` 행이고, 인천·김포는 픽스처·예시에만 나온다.
