/**
 * no-hangul-literal 예외 목록(명시) — 화면 문자열이 아닌 한글 값만 둔다. 화면 문구는 전부 src/i18n/ko.json.
 *
 * 값을 추가할 때(테스트 `no-hangul-literal.test.js` 가 근거를 확인한다):
 *  - CONTRACT_ENUM_VALUES: contracts/openapi.bundled.yaml 의 enum 값이어야 한다(서버와 주고받는 값 — 비교·타입·옵션 값).
 *    화면에 보일 때는 enumText()/labelText() 로 ko.json 을 거친다.
 *  - CONTRACT_MARKERS: enum 이 아닌 서버 데이터 표식(사유 문자열·단위 접미어·발췌 표식). 값 → 그 문자열이 그대로 있는
 *    저장소 파일(계약 스키마 또는 서버 구현). 프론트가 서버 값과 **같은지 비교**하려고 쓰는 것만.
 *  - DEV_ERROR_MESSAGES: 사용자 화면에 나오지 않는 개발자용 오류(`throw new Error(…)`) — 메시지 → frontend/ 기준 파일.
 *    규칙은 이 문장이 내장 Error 생성자 인자일 때만 허용한다.
 */

/** 계약 enum 값(contracts/openapi.bundled.yaml) */
export const CONTRACT_ENUM_VALUES = [
  // Label
  '확인됨',
  '추정',
  '비공식',
  '재가공',
  '확인 불가',
  '검증 모순',
  // IntakeStatus
  '가능',
  '미정',
  '불가',
  // JudgeScope
  '판정 대상',
  '보류',
  '참고',
  '미해결',
  '제외',
  // inclusion_class(한글 값)
  '범위 경계',
  '미분류',
  // ChecklistItem.kind
  '법적 확인',
  '중도금',
  '만료',
  '공고 예상',
  '계약',
  '사실 재확인',
  // HumanCheck.entered_by
  '운영자',
  '검토자',
  // Catalyst.stage · kind
  '확정',
  '계획',
  '추진',
  '언론',
  '미확정',
  '호재 아님',
  // RemainingEvent.kind
  '본청약',
  '무순위',
  '임의',
  '선착순',
  // Requirement status
  '충족',
  '미충족',
  '미입력',
  // Scenario.purpose
  '실거주',
  '시세차익',
  '병행',
];

/** 서버 데이터 표식(enum 아님) → 그 문자열이 있는 저장소 경로(저장소 루트 기준) */
export const CONTRACT_MARKERS = {
  // complex.land_type(자유 문자열 — 스키마 설명·예시 값)
  공공택지: 'contracts/schemas/complex.json',
  민간택지: 'contracts/schemas/complex.json',
  // 사람 확인 숫자 단위 접미어(서버 parse_human_value allowed)
  개월: 'backend/app/api/demotion.py',
  년: 'backend/app/api/demotion.py',
  원: 'backend/app/api/demotion.py',
  // 접수 사유(계약 .16·.17 F4)
  '공식 홈페이지가 다른 단지': 'backend/app/scheduler/pipeline.py',
  '공식 홈페이지 동일성 미확인': 'backend/app/scheduler/pipeline.py',
  // 채택 보류 표식(normalize CONFLICT_HOLD, 계약 .16 S2)
  '출처 상충 — compare 대기': 'backend/app/core/protocols.py',
  // 가격 출처 발췌의 단위 근거 줄 표식(계약 .16 F6)
  '[단위 근거] ': 'backend/app/normalize/notice_parser.py',
};

/** 개발자용 오류 메시지(throw new Error) → frontend/ 기준 파일 */
export const DEV_ERROR_MESSAGES = {
  '#root 없음': 'src/main.tsx',
  'useTheme은 ThemeProvider 안에서만 쓴다': 'src/lib/theme.tsx',
};
