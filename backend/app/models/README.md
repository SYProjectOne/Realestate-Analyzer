# app/models

- **주인**: WP0 (CEO, WP0-A 계약)
- **읽기 허용**: 전체
- 쓰기 금지 이유(RA §2): 모델은 계약 마이그레이션(`contracts/migrations/versions/`)과 1:1 이다. 컬럼이 더 필요하면
  완료 보고의 '계약 변경 요청'으로 남긴다(AGENTS 규칙 2). 마이그레이션은 이 패키지를 import 하지 않는다(D14-9).

| 모듈 | 테이블 |
| --- | --- |
| `base.py` | `Base`·이름 규칙(`NAMING_CONVENTION`) |
| `region.py` | region · snapshot · snapshot_view · snapshot_view_unit(발행 저장본) |
| `reference.py` | 법정동·행정동·매핑·세대수 참조 표 |
| `raw.py` | raw_document · field_provenance |
| `complex.py` | complex · complex_type · payment_terms · competition · remaining_event · intake_status |
| `market.py` | rtms_trade · benchmark · comparable_set · supply · unsold · catalyst · catalyst_link |
| `judgment.py` | judgment_log · claim · fact_demotion |
| `analysis.py` | scenario · score_run · score_component · score_total · ladder · decision |
| `ops.py` | job_run · change_event · checklist_item · human_check · share_link |

검사: 모델 ↔ 마이그레이션 head 일치는 `backend/tests/contracts`(SQLite·Postgres autogenerate 비교)가 본다.
