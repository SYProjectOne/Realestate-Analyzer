# R3d 수정 — 4차 리뷰(`R3_REVIEW4.md`) (계약 .8 → .9)
방식: R3c처럼 백엔드 핵심은 1명(CORE2), 프론트 1명(FE3). minor는 각자 소유 범위에서 전부. 결정 D12.
=====CORE2=====
소유: `backend/**`, `contracts/**`(계약 .9), `infra/**`, `docs/runbook.md`, `scripts/tasks.py`. Critical 1~4, Major 1~14·16(서버)·17, D12 전부, 백엔드 minor 전부(보안·강등·오버레이·리비전·백업·이름 키·호재·할인·운영·테스트), t13 간헐 실패 수정, runbook D11·D12 반영, `infra/README.md`. 리뷰 재현 사례마다 실제 동작 테스트 + 영역 횡단 통합 테스트(새 공고 동일 모순 가격 → 강등 유지; 사람 확인 후 새 공식 공고 다른 값 → 채택+재검토 항목; 할인 추정이면 모든 경로 미차감 일치; 리비전 3개 만들고 옛 리비전 응답 바이트 불변).
=====FE3=====
소유: `frontend/**`, `e2e/**`. Critical 5(G5 '이후' = 새 리비전), Major 15(잡 완료 후 regions·스냅샷 목록 무효화 — 새로 고침 없는 리비전 전환 테스트), 16(화면: 보고서 비교 선택에 리비전 표시·building 제외), 화면 minor 전부(sampleCountFact 라벨, closed_by, 할인 문구 모바일, 409 후 재조회, eslint 별칭 우회, `la_1` 노출→생활권 이름), G5 실 API·G8 리비전 e2e. 계약 .9가 머지되면 gen 재생성 후 맞춤.
