# app/normalize

- **주인**: WP2
- **읽기 허용**: WP1, WP7
- 쓰기 금지 이유(RA §2): —

## 범위 (RA §2·§5, DECISIONS D2)

원문 → 필드 후보 → 상충 해결 → 출처 행. 숫자 하나도 출처 없이 남기지 않는다.

| 모듈 | 내용 |
| --- | --- |
| `fields.py` | RA §3 출처 우선순위 표(`source_rank`), 수치 필드 목록(provenance 전수 검사 대상), change_event critical 필드 |
| `notice_parser.py` | 공고문 텍스트(pdfplumber) → 머리 표(전매·거주·재당첨·상한제·택지·규제), 일정, 공급대상 표, 공급금액 표(타입별 최고가·최저층가, 행 배정은 타입 세대수 합으로 검증), 계약금·중도금·잔금·1차 정액·중도금 회차 날짜, 발코니, 선택품목(필수 옵션 0), 입주월. 못 읽은 필드는 `needs_extract` |
| `applyhome_parser.py` | 청약홈 목록·상세·경쟁률 HTML → 후보(세대수·면적·일정·경쟁률 rank 1, 최고가 rank 2) |
| `official_site_parser.py` | 공식 홈페이지 DOM 텍스트 → 접수 상태 **문구 후보**(분류는 판정기/사람) |
| `rtms_parser.py` | 실거래 Open API XML(신·구 태그) → rtms_trade 후보(Open API 확인됨 rank 1 / 재가공 rank 2) |
| `stats_parser.py` | 미분양 CSV → unsold 후보 |
| `resolver.py` | `PriorityResolver` — chosen, conflict_group, needs_compare(같은 rank·다른 출처 종류의 1차·1차만) |
| `provenance.py` | field_provenance upsert(삭제 없음), 수치 필드 전수 검사(`missing_provenance`), `fact_for` |
| `changes.py` | 이전값 diff → change_event (새 공고·가격·계약금·중도금일 = critical), 현재 납부 조건 |
| `extract_request.py` | `needs_extract` 후보 → 판정기 extract 요청 데이터(≤2,000자, 호출은 WP3) |
| `judged.py` | 판정 결과 반영(계약 2026-10-09.3): `apply_extracted`(extract auto + 감사 통과 = 확인됨, 감사 전 = 추정, review·감사 flagged = 미반영) · `apply_compare`(contradicts → 1차 공고 자료 채택·병기, conflict_group 유지) |
| `store.py` | `store_raw_document(session, raw)` — 후보 → 키 묶기 → (같은 필드 옛 출처 재파싱) → resolve → upsert + provenance + change_event, SAVEPOINT 한 트랜잭션 |
| `archive.py` | 월별 목록·상세·경쟁률·공고 원문 색인(manifest.json)과 결정적 zip, 아카이브 공고 찾기 |
| `region_resolve.py` | 자유 지명 → `RegionCandidate[]`(순수 함수 + DB 래퍼), 선택 → 시도·시군구·법정동 코드 |
| `living_area.py` | 기본 생활권(시군구당 1), 편집 검증·적용, 주소 → 법정동·생활권 배정(지역 밖 = 범위 경계), 세대수 집계(1:N 균등 분할, 추정·주민등록 세대) |

## 쓰는 법 (WP1·WP5·WP7)

```python
from app.normalize.store import store_raw_document

res = store_raw_document(session, raw_document_row_or_dto, snapshot_id=sid)  # commit은 호출자
res.change_events  # critical이면 triggers_rejudge
res.resolved.needs_compare  # True면 WP3가 그 conflict 그룹에 compare
res.extract_requests  # WP3 extract로 넘길 데이터

from app.normalize.region_resolve import resolve_region_db  # GET /regions/resolve
from app.normalize.living_area import apply_living_area_edit, LivingAreaError  # PUT living-areas (422)
from app.normalize.living_area import region_household_facts  # LivingArea.households Fact
```

- `Parser.parse(raw) -> list[FieldCandidate]`, `Resolver.resolve(candidates) -> ResolvedFields` (RA §4-3).
- entity_key: complex = 주택관리번호(임의공급·무순위 공고는 **최초** 주택관리번호), complex_type = `<번호>:<약식 타입>`,
  payment_terms = `<번호>:<이 공고 번호>`, competition = `<번호>:<공급형태>:<순위 지역>:<타입>`.
- 경쟁률 원문 URL에는 `houseManageNo`가 있어야 한다(페이지 본문에 번호가 없다).
- 파싱 정규식은 판단이 아니다(규칙 3). 포함 여부·상충 판단·접수 상태 분류는 판정기(WP3) 몫이다.
- 원문 파일은 `app.core.paths.resolve_raw_path(relpath)` 로 연다.

## 규칙

- 이 디렉터리와 `backend/tests/normalize/` 만 주인이 쓴다. 다른 WP는 읽기만 하고, 고칠 것은 요청으로 남긴다(AGENTS 규칙 1).
- 공통 도구는 `app.core` 를 쓴다(`app/core/README.md`). 모델·계약은 `app/models`, `contracts/` (WP0) — 읽기 전용.
- 지역명 하드코딩 금지(규칙 15) — 지역 이름은 참조표(legal_dong·admin_dong)에서만 온다.
