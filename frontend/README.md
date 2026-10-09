# frontend — 웹 GUI (React 18 + TS + Vite)

| 경로                                                                                                                                                                                           | 주인                         |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------- |
| `package.json`, `package-lock.json`, 도구 설정(vite·tsconfig·eslint·tailwind·playwright), `scripts/`, `eslint-rules/`, `src/api/`, `src/mocks/`, `src/layout/`, `src/hooks/`, `src/routes.tsx` | WP0 (WP0-C 스캐폴드)         |
| `src/pages/`                                                                                                                                                                                   | WP6a                         |
| `src/components/`, `src/charts/`                                                                                                                                                               | WP6b — 계약은 각 폴더 README |

## 명령

```bash
npm ci
npm run gen:api     # openapi → src/api/schema.d.ts (생성물, 손으로 고치지 않음)
npm run gen:msw     # openapi response example(s) → src/mocks/handlers.gen.ts (생성물)
npm run dev         # API 프록시(/api → http://localhost:8000, API_PROXY_TARGET로 변경)
npm run dev:msw     # API 없이 MSW 목 응답
npm test | npm run lint | npm run typecheck | npm run build
npm run e2e         # Playwright(MSW 모드 dev 서버 자동 기동). 최초 1회 npx playwright install chromium
```

## 계약 전환 (WP0-A 머지 후)

`openapi.config.json`의 `"source": "fixture"` → `"contract"` 한 줄. 그러면 `../contracts/openapi.bundled.yaml`(있으면) 또는 `../contracts/openapi.yaml`을 읽는다. 일회성으로는 `OPENAPI_SOURCE=contract npm run gen:api`.
그 다음 `src/api/types.ts`의 임시 타입을 `components['schemas'][...]` 별칭으로 바꾼다(화면·차트는 types.ts만 import 하므로 여기서 끝난다).

## 규칙

- 화면 문자열은 `src/i18n/ko.json` + `t()`. 숫자는 `FactCell` 또는 `src/lib/format.ts` — ESLint `local/no-raw-number-render`가 강제.
- 지역명 하드코딩 금지(목 데이터·테스트 제외). 라벨은 텍스트 배지. 하단 고정 문구는 레이아웃이 붙인다.
