/**
 * no-hangul-literal — "화면 문자열은 src/i18n/ko.json 한 곳"(AGENTS 규칙 12, R5-FE 3·D25-1) 자동 검사.
 *
 * src 의 TS/TSX 에서 한글이 든 문자열을 거부한다(ko.json 은 JSON 이라 린트 대상이 아니다):
 *  1. JSX 텍스트(`<p>안녕</p>`) — 언제나 금지. enum 값도 enumText()/t() 를 거쳐 보인다.
 *  2. 문자열 리터럴·템플릿(JSX 속성·식, TS 모듈 상수, 타입 리터럴, 객체 키 포함) — 아래 명시 예외만 허용.
 *
 * 예외(명시 목록, eslint-rules/hangul-allowlist.js — 테스트가 근거를 확인한다):
 *  - 계약 enum 값과 **정확히 같은** 문자열(CONTRACT_ENUM_VALUES): 서버와 주고받는 값(비교·타입·옵션 값).
 *  - 서버 데이터 표식(CONTRACT_MARKERS): 사유 문자열·단위 접미어·발췌 표식처럼 서버 값과 같은지 비교하는 것.
 *  - 개발자용 오류(DEV_ERROR_MESSAGES): 내장 Error 생성자(`new Error`·`TypeError`·`RangeError`) 인자일 때만.
 *    앱 오류 클래스(ApiError 등)는 message 가 화면에 보일 수 있어 대상이 아니다.
 *  - 식이 든 템플릿(`${n}건`)은 enum·표식일 수 없으므로 언제나 금지.
 * 예외 파일(DEFAULT_EXCEPT): 테스트(*.test.*)·src/test/·MSW 목(src/mocks/, 계약 예시 응답)·차트 갤러리
 *   (src/charts/gallery/, dev·MSW 모드 전용 `/__charts` 시각 회귀 도구 — 프로덕션 번들 라우트 없음).
 * 옵션 { exceptFiles?: string[](정규식 소스), allow?: string[](추가 허용 값) }.
 */
import { CONTRACT_ENUM_VALUES, CONTRACT_MARKERS, DEV_ERROR_MESSAGES } from './hangul-allowlist.js';

/** 한글 음절·자모·호환 자모 */
export const HANGUL = /[ᄀ-ᇿ㄰-㆏ꥠ-꥿가-힯ힰ-퟿]/;

export const DEFAULT_EXCEPT = [
  String.raw`\.test\.[jt]sx?$`,
  String.raw`(^|[\\/])src[\\/]test[\\/]`,
  String.raw`(^|[\\/])src[\\/]mocks[\\/]`,
  String.raw`(^|[\\/])src[\\/]charts[\\/]gallery[\\/]`,
];

const BUILTIN_ERRORS = new Set(['Error', 'TypeError', 'RangeError']);

const ALLOWED_VALUES = new Set([...CONTRACT_ENUM_VALUES, ...Object.keys(CONTRACT_MARKERS)]);
const DEV_MESSAGES = new Set(Object.keys(DEV_ERROR_MESSAGES));

/** 리터럴이 `new Error('…')`(내장 오류 생성자)의 인자인가 */
function isBuiltinErrorArgument(node) {
  const parent = node.parent;
  return (
    !!parent &&
    parent.type === 'NewExpression' &&
    parent.callee.type === 'Identifier' &&
    BUILTIN_ERRORS.has(parent.callee.name) &&
    parent.arguments.includes(node)
  );
}

function preview(text) {
  const oneLine = text.replace(/\s+/g, ' ').trim();
  return oneLine.length > 40 ? `${oneLine.slice(0, 40)}…` : oneLine;
}

/** @type {import('eslint').Rule.RuleModule} */
const rule = {
  meta: {
    type: 'problem',
    docs: {
      description:
        '화면 문자열은 src/i18n/ko.json 한 곳 — JSX·TS 의 한글 문자열 금지(계약 enum·서버 표식·개발자 오류는 명시 예외)',
    },
    schema: [
      {
        type: 'object',
        properties: {
          exceptFiles: { type: 'array', items: { type: 'string' } },
          allow: { type: 'array', items: { type: 'string' } },
        },
        additionalProperties: false,
      },
    ],
    messages: {
      hangulJsxText:
        "JSX 안 한글 문구 '{{text}}' 금지 — 화면 문자열은 src/i18n/ko.json 에 두고 t('…')(enum 값은 enumText)로 쓴다 (no-hangul-literal).",
      hangulLiteral:
        "한글 문자열 '{{text}}' 금지 — 화면 문자열은 src/i18n/ko.json(t('…')). 계약 enum 값·서버 표식·개발자 오류면 eslint-rules/hangul-allowlist.js 에 근거와 함께 추가한다 (no-hangul-literal).",
    },
  },

  create(context) {
    const options = context.options[0] ?? {};
    const filename = context.filename ?? context.getFilename();
    const except = (options.exceptFiles ?? DEFAULT_EXCEPT).map((source) => new RegExp(source));
    if (except.some((re) => re.test(filename))) return {};
    const extra = new Set(options.allow ?? []);

    const allowedValue = (text) => ALLOWED_VALUES.has(text) || extra.has(text);

    const checkString = (node, text) => {
      if (!HANGUL.test(text)) return;
      if (allowedValue(text)) return;
      if (DEV_MESSAGES.has(text) && isBuiltinErrorArgument(node)) return;
      context.report({ node, messageId: 'hangulLiteral', data: { text: preview(text) } });
    };

    return {
      JSXText(node) {
        if (!HANGUL.test(node.value)) return;
        context.report({ node, messageId: 'hangulJsxText', data: { text: preview(node.value) } });
      },
      Literal(node) {
        if (typeof node.value !== 'string') return;
        // import/export 경로는 문자열이 아니라 모듈 지정자
        const p = node.parent;
        if (
          p &&
          (p.type === 'ImportDeclaration' ||
            p.type === 'ExportNamedDeclaration' ||
            p.type === 'ExportAllDeclaration' ||
            p.type === 'ImportExpression')
        ) {
          return;
        }
        checkString(node, node.value);
      },
      TemplateLiteral(node) {
        if (node.expressions.length === 0) {
          checkString(node, node.quasis.map((q) => q.value.cooked ?? q.value.raw).join(''));
          return;
        }
        const text = node.quasis.map((q) => q.value.cooked ?? q.value.raw).join('${…}');
        if (!HANGUL.test(text)) return;
        context.report({ node, messageId: 'hangulLiteral', data: { text: preview(text) } });
      },
    };
  },
};

export default rule;
