# contracts/fixtures — 회귀 픽스처 계약 (RA §4-5, §9)

주인: **WP9**(R1에서 만든다). WP0-A는 이 README와 `incheon_gimpo_2026-10-08/expected_scores.json` 시드만 둔다.
픽스처를 고치면 회귀가 맞는 것처럼 보일 수 있으므로, 고칠 때는 사유를 `contracts/CHANGELOG.md`에 적는다.

## 디렉터리

```
contracts/fixtures/
├─ incheon_gimpo_2026-10-08/        # 기준일 2026-10-08 (보고서 기준일 2026-10-07과 같은 데이터)
│  ├─ region.json                   # Region (contracts/schemas/region.json) — 아래 '지역 정의'
│  ├─ complexes.json                # ComplexBundle[16] (schemas/complex.json#/$defs/ComplexBundle), 모든 수치 Fact
│  ├─ expected_scores.json          # RA §9 (a)단계 골든 (schemas/expected_scores.json) ← WP0-A 시드
│  ├─ expected_scores_v2.json       # (b)단계: §6-4 식 재계산 값, R1 끝에 사람 확인 후 고정
│  ├─ judgments/
│  │  ├─ _meta.json                 # {"adapter_version": "mock-fixture-2026-10-08", "recorded_at", "source", "note", "index"}
│  │  ├─ _index.json                # 녹화 목록 [{judgment_seq, tool, purpose, input_hash, file, report_ref, payload}]
│  │  └─ <tool>/<hex>.json          # JudgmentEnvelope 1개. <hex> = input_hash에서 'sha256:'를 뺀 64자
│  ├─ raw/                          # 공고문 txt 발췌, 공식 홈페이지 응답(403 포함) 녹화, 청약홈 HTML
│  └─ http/                         # respx 녹화(수집기 테스트용, WP1)
├─ reference/                       # DECISIONS D2-1 참조 파일 사본(법정동·행정동·매핑·세대 현황, 공공누리 1유형)
└─ ocr_samples/                     # DECISIONS D5 OCR 평가 시료(정답 텍스트 동봉)
```

## MockAdapter 규칙 (WP3)

1. `JudgeAdapter`와 같은 9개 메서드. `adapter_version`은 `judgments/_meta.json`의 값을 그대로 쓴다(녹화와 해시를 맞추기 위해).
   인천·김포 픽스처의 값은 **`"mock-fixture-2026-10-08"`** — MockAdapter 전용 고정 문자열이다. 실제 어댑터의
   `"<코드>+jev-mcp@<서버>+<model>"`(DECISIONS D6)과 일부러 다르다: 녹화 payload가 보고서 재구성이라 실제 판정기 hash와 섞이면 안 된다.
   이 값을 바꾸면 모든 input_hash·파일 이름이 바뀐다(생성기 `tools/build_incheon_gimpo.py`의 `ADAPTER_VERSION`).
   `judgments/_index.json`은 녹화 전부의 목록 `[{judgment_seq, tool, purpose, input_hash, file, report_ref, payload}]`(seq 순)이다 —
   payload·purpose·adapter_version으로 `app.core.protocols.input_hash`를 다시 계산하면 `input_hash`·`file`과 같고, Fact의 `prov='jl_<seq>'`가 가리키는 출처표다.
2. 호출마다 `app.core.protocols.input_hash(tool, purpose, payload, adapter_version)`을 계산해
   `judgments/<tool>/<hex>.json`을 찾는다. 있으면 그 봉투를 `cached=True`로 돌려준다.
3. **없으면 `status="review"`** 봉투(`result={}`, `raw={"reason": "no recording"}`, `confidence=None`)를 돌려준다 —
   테스트가 조용히 통과하는 일은 없다. 예외를 던지지 않는다(`JudgeUnavailable`은 다운 시뮬레이션 전용, T18).
4. 녹화 파일은 `contracts/schemas/judgment_envelope.json`으로 검증된다.

## 지역 정의 (DECISIONS D3)

인천 연수구(송도동) · 검단구(검단: 원당·당하·마전·불로·오류·왕길 등) · 계양구 + 김포시.
2026-07 검단구 분구 이후 보고서는 '검단구'를 쓴다. 공식 법정동코드 전체자료(`reference/legal_dong_full.zip`)도 서구(28260)를
폐지하고 검단구(28290)를 두므로 픽스처·예시는 **검단구 현행 코드**를 쓴다(계약 2026-10-09.2). 법정동 표가 아직 옛 서구 코드만
가진 환경이면 `GET /regions/resolve?q=검단`에서 서구 후보가 나와야 하고, 둘 다 active면 둘 다 나와야 한다(D3).
생활권 기본값은 시군구 1개당 1개(연수구 / 검단구 / 계양구 / 김포시).

## expected_scores.json (RA §9 (a)단계)

- 원천: `docs/source/incheon_gimpo_report.md` §12-4-3 통합 종합 점수표(16 후보: 점수 12 + 보류 2 + 참고 2), §12-4-2 통합 rerank(#124),
  §6-3·§6-5 인천 8후보(#71), §12-5-2 상황별 decide(#125~129).
- 기본 가중치(0.35/0.20/0.15/0.10/0.10/0.10), 동점 규칙(|ΔS| < 0.05 공동 순위), 허용 오차 ±0.01.
- **T1** = 그란테르 5.87 > 엘리프 5.70 > 한내들 5.33 > 스위첸(김포) 5.00 > 센트레빌 = 더샵 AB23 4.61 — 보고서 §12-4-3과 같다.
- **T2** = 상황 B decide #127: 칸타빌 0.54, 엘리프 0.42, confidence 0.48 → tie.
- 보고서와 RA 규칙이 다른 곳은 파일의 `discrepancies`에 둘 다 적었다(§6-5의 5.73·5.35, 9~11위 공동 순위, rerank 식).
- `complex_id` 1~16은 `contracts/examples/*.json`(MSW)과 같은 번호다. 픽스처 DB를 만들 때도 이 번호를 쓰면 예시와 맞는다.
