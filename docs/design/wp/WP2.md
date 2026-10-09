# WP2 정규화·저장 — 작업 지시

소유: `backend/app/normalize/`, `backend/tests/normalize/`.
참조: RA §3 전체(특히 `field_provenance`, 출처 우선순위·상충 처리 표, 스냅샷 규칙), §4-3 `Parser`·`Resolver`, §5 WP2 카드, §6-1, §9 T5·T9·T13; DECISIONS D2(지역 해석·생활권·법정동 배정·세대수), D2-6.

## 할 일 (RA 카드 + DECISIONS 확장)
1. `applyhome_parser.py`, `notice_parser.py`(가격표 타입·층·공급금액, 발코니, 옵션, 납부 조건, 전매·거주·재당첨, 입주월: 정규식+표 파서; 실패 필드는 판정기 extract 요청 payload(데이터만, `judge/` 호출 없음)로 넘김), `official_site_parser.py`(접수 상태 텍스트 후보), `rtms_parser.py`, `stats_parser.py`. 수집기 코드(WP1)는 아직 없다 — `RawDocument` 계약과 실제 청약홈·공고문 원문 샘플(직접 받아서 `tests/normalize/fixtures/`에 저장)로 작업.
2. `resolver.py`: §3 우선순위로 chosen, conflict_group, 1차·1차 상충만 `needs_compare=True`.
3. `provenance.py`: 모든 수치 필드 → `field_provenance` 행(URL·확인일·라벨·원문 발췌 오프셋).
4. `changes.py`: 이전값 diff → `change_event`(새 공고·가격·계약금·중도금일 = critical).
5. `archive.py`: 월별 목록·공고·경쟁률 스냅샷 보관.
6. **지역(D2)**: `region_resolve.py` — 자유 지명 → `RegionCandidate[]`(legal_dong/admin_dong/시군구/시도 이름 매칭: 공백·접미사 무시, exact > prefix > partial, 행정동이면 매핑된 법정동 목록) — 순수 함수 + DB 래퍼. `living_area.py` — 기본 생활권(시군구당 1개), 편집 검증(모든 법정동이 정확히 한 생활권), 단지 주소 → 법정동 코드 배정, 생활권 세대수 집계(1:N 균등 분할, 라벨 "추정(주민등록 세대)").
7. `store.py`: RawDocument 1개 → 후보 → resolve → upsert + provenance + change_event를 한 트랜잭션으로(`app.models` 사용).

## 완료 기준
- [ ] 인천·김포 공고문 발췌 픽스처(최소 8개 단지; `docs/source/incheon_gimpo_report.md`와 실제 청약홈 공고문에서 만듦) → `complex_type` 가격이 기대값과 원 단위 일치
- [ ] 해링턴 1,573 vs 1,769 → conflict_group 1건 + chosen=청약홈 (T5)
- [ ] 모든 수치 필드 provenance 행 존재 전수 검사
- [ ] 임의공급 계약금 10%→5% → payment_terms 2행 + change_event critical (T9)
- [ ] region_resolve: "송도"→송도동(연수구), "검단"→행정동 + 법정동 후보, "김포시"→시군구, "연수구" exact 우선 — 참조 데이터는 테스트용 소형 CSV를 `tests/normalize/fixtures/`에 직접 만든다
- [ ] 생활권 편집 검증(중복·누락 오류), 주소 → 법정동 배정, 세대수 집계 라벨
