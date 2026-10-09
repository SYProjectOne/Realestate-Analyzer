# e2e — 사용자 흐름 e2e · T16 성능 측정

- **주인**: WP9 (`AGENTS.md` 소유 표: `e2e/`, `contracts/fixtures/`). **읽기 허용**: 모든 WP.

| 경로 | 내용 |
| --- | --- |
| `flows/` | R3 사용자 흐름(실제 API + devseed DB + Mock 판정기): G8 보고서 PDF, G7 사람 확인 → 재판정, G0 지역 부트스트랩 |
| `perf/` | T16 화면 성능 측정(D10-8: 가상 스크롤 p50 ≤ 17ms, p95 ≤ 34ms) |
| `support/` | 오프라인 수집·참조 데이터·재생 worker(파이썬 보조 스크립트) |
| `env.ts`, `playwright.config.ts` | 실행마다 포트·작업 폴더를 따로 잡는 설정(병렬 실행 격리) |

## 명령

```bash
npm ci
npm test        # 흐름 e2e (playwright test)
npm run perf    # T16 측정
npm run typecheck
```
