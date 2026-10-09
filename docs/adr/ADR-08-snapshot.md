# ADR-08 스냅샷

- 상태: 채택 (RA v1 §1, DECISIONS D1 #14)
- 결정: **모든 파생 테이블에 `snapshot_id`(기준일); 원문은 `/data/raw/{source}/{yyyy-mm-dd}/{sha256}.{ext}`**
- 버린 대안: 행 덮어쓰기

## 이유

보고서 diff 와 "어제와 무엇이 달라졌나"가 요구사항이다.

## 결과

- 기준일 = Asia/Seoul 달력 날짜(`core.time.today_kst()`, `core.snapshot.base_date()`).
- 원문 경로: `core.paths.raw_path(source, day, sha256, ext)`; DB 에는 RAW_DIR 기준 상대 경로(`raw_relpath`)를 저장하고
  `resolve_raw_path` 로 연다(경로 탈출 차단). 개발 `./data/raw`, 컨테이너 `/data/raw`(`rawdata` 볼륨).
- 저장은 `core.snapshot.store_raw` — 임시 파일 → rename(원자적), 같은 sha256 이면 쓰지 않음(멱등).
- 보존 기간 무기한, 삭제 없음; 디스크 부족 시 월별 압축(runbook §6).

## 바꿀 신호

없음.
