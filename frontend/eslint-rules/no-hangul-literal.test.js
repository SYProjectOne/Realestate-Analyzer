// @vitest-environment node
/**
 * R5-FE 3(D25-1): 화면 문자열 ko.json 단일화 자동 검사(AGENTS 규칙 12).
 * JSX·TS(X) 의 한글 문자열 리터럴을 거부하고, 예외는 명시 목록(hangul-allowlist.js)만 — 계약 enum 값·서버 표식·개발자용 오류 메시지.
 */
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { ESLint, RuleTester } from 'eslint';
import tseslint from 'typescript-eslint';
import YAML from 'yaml';
import { afterAll, describe, expect, it } from 'vitest';
import { CONTRACT_ENUM_VALUES, CONTRACT_MARKERS, DEV_ERROR_MESSAGES } from './hangul-allowlist.js';
import rule, { DEFAULT_EXCEPT, HANGUL } from './no-hangul-literal.js';

RuleTester.afterAll = afterAll;
RuleTester.describe = describe;
RuleTester.it = it;
RuleTester.itOnly = it.only;

const ruleTester = new RuleTester({
  languageOptions: {
    parser: tseslint.parser,
    parserOptions: { ecmaFeatures: { jsx: true } },
  },
});

const file = 'src/pages/dashboard/index.tsx';
const valid = (code, filename = file) => ({ code, filename });
const invalid = (code, messageId, filename = file, count = 1) => ({
  code,
  filename,
  errors: Array.from({ length: count }, () => ({ messageId })),
});

ruleTester.run('no-hangul-literal', rule, {
  valid: [
    // 화면 문구는 t(key)
    valid("<h1>{t('page.G1.title')}</h1>"),
    valid("<span title={t('a.b')}>{name}</span>"),
    valid('<span>{row.name} ×</span>'),
    valid("const s = 'plain ascii';"),
    // 계약 enum 값(라벨·접수 상태·판정 범위 …) — 비교·타입·옵션 값
    valid("if (fact.label === '확인 불가') return null;"),
    valid("const x = status === '가능' ? 'a' : 'b';"),
    valid("type P = '실거주' | '시세차익' | '병행';"),
    valid("const LABELS = ['확인됨', '추정'] as const;"),
    valid("const m = { '확인 불가': 1 };"),
    valid('<option value="가능" />'),
    valid('const s = `확정`;'),
    // 서버 표식(계약 데이터 모양)
    valid("const MARK = '[단위 근거] ';"),
    valid("const r = '공식 홈페이지가 다른 단지';"),
    // 개발자용 오류 메시지 — throw new Error(…) 안의 명시 목록만
    valid("if (!root) throw new Error('#root 없음');"),
    valid("throw new Error('useTheme은 ThemeProvider 안에서만 쓴다');"),
    // 예외 파일: 테스트·MSW 목·차트 갤러리(dev 전용)·테스트 설정
    valid('<p>한글 문구</p>', 'src/pages/foo.test.tsx'),
    valid("const x = '한글';", 'src/mocks/handlers.extra.ts'),
    valid("const x = '한글';", 'C:\\repo\\frontend\\src\\mocks\\handlers.gen.ts'),
    valid("<p>{'설명 문구'}</p>", 'src/charts/gallery/ChartGallery.tsx'),
    valid("const x = '한글';", 'src/test/setup.ts'),
    // 옵션: 예외 파일·추가 허용
    {
      code: "const x = '임시';",
      filename: 'src/stories/a.tsx',
      options: [{ exceptFiles: ['stories'] }],
    },
    { code: "const x = '임시';", filename: file, options: [{ allow: ['임시'] }] },
  ],
  invalid: [
    // JSX 텍스트는 enum 값이어도 거부(enumText/t 를 거친다)
    invalid('<p>안녕하세요</p>', 'hangulJsxText'),
    invalid('<Badge>확정</Badge>', 'hangulJsxText'),
    invalid('<p>{count}개</p>', 'hangulJsxText'),
    // JSX 속성·식 안의 문구
    invalid('<span title="툴팁 문구" />', 'hangulLiteral'),
    invalid('<input aria-label="검색" />', 'hangulLiteral'),
    invalid("<p>{'불러오는 중'}</p>", 'hangulLiteral'),
    invalid("<p>{ok ? '성공' : '실패'}</p>", 'hangulLiteral', file, 2),
    // TS 모듈의 문구(변수에 담았다가 렌더하는 우회)
    invalid("const MSG = '저장했습니다';", 'hangulLiteral', 'src/lib/messages.ts'),
    invalid("toast('저장했습니다');", 'hangulLiteral'),
    // enum 값이 문장 일부면 거부(정확히 같은 값만 허용)
    invalid("const s = '확인 불가 사유';", 'hangulLiteral'),
    // 템플릿: 식이 있으면 enum 일 수 없다
    invalid('const s = `${n}건 확인`;', 'hangulLiteral'),
    invalid('<p>{`총 ${n}`}</p>', 'hangulLiteral'),
    // 개발자 오류 목록에 없는 메시지·오류 밖의 같은 문장
    invalid("throw new Error('사용자에게 보일 수 있는 문장');", 'hangulLiteral'),
    invalid("const m = '#root 없음';", 'hangulLiteral'),
    // 앱 오류 클래스(ApiError 등)는 화면에 message 가 보일 수 있다 — 목록 대상 아님
    invalid("throw new ApiError('#root 없음');", 'hangulLiteral'),
    // 예외 파일이 아닌 곳(ko.json 이 아닌 i18n 모듈 포함)
    invalid("const x = '한글';", 'hangulLiteral', 'src/i18n/index.ts'),
  ],
});

const here = dirname(fileURLToPath(import.meta.url));
const repo = join(here, '..', '..');

/** contracts/openapi.bundled.yaml 의 모든 enum(·const) 문자열 */
function contractEnumStrings() {
  const doc = YAML.parse(readFileSync(join(repo, 'contracts', 'openapi.bundled.yaml'), 'utf8'));
  const out = new Set();
  const walk = (node) => {
    if (Array.isArray(node)) return node.forEach(walk);
    if (!node || typeof node !== 'object') return;
    for (const [key, value] of Object.entries(node)) {
      if (key === 'enum' && Array.isArray(value)) {
        for (const v of value) if (typeof v === 'string') out.add(v);
      }
      if (key === 'const' && typeof value === 'string') out.add(value);
      walk(value);
    }
  };
  walk(doc);
  return out;
}

describe('예외 목록(hangul-allowlist.js)은 근거가 있는 값만', () => {
  it('계약 enum 값은 전부 contracts/openapi.bundled.yaml 의 enum 이다', () => {
    const enums = contractEnumStrings();
    const missing = CONTRACT_ENUM_VALUES.filter((v) => !enums.has(v));
    expect(missing).toEqual([]);
    expect(CONTRACT_ENUM_VALUES.every((v) => HANGUL.test(v))).toBe(true);
  });

  it('서버 표식은 적힌 출처 파일에 그 문자열이 그대로 있고, enum 과 겹치지 않는다', () => {
    const enums = contractEnumStrings();
    for (const [value, source] of Object.entries(CONTRACT_MARKERS)) {
      const text = readFileSync(join(repo, source), 'utf8');
      expect({ value, found: text.includes(value) }).toEqual({ value, found: true });
      expect(enums.has(value)).toBe(false);
    }
  });

  it('개발자 오류 메시지는 적힌 파일의 throw new Error(…) 안에 있다', () => {
    for (const [message, source] of Object.entries(DEV_ERROR_MESSAGES)) {
      const text = readFileSync(join(here, '..', source), 'utf8');
      expect({ message, found: text.includes(`new Error('${message}')`) }).toEqual({
        message,
        found: true,
      });
    }
  });

  it('예외 파일은 테스트·목·갤러리·테스트 설정뿐(ko.json 밖 화면 코드는 예외가 아니다)', () => {
    const except = DEFAULT_EXCEPT.map((s) => new RegExp(s));
    const skipped = (f) => except.some((re) => re.test(f));
    for (const f of [
      'src/pages/a.test.tsx',
      'src/mocks/handlers.gen.ts',
      'src/charts/gallery/fixtures.ts',
      'src/test/render.tsx',
    ]) {
      expect({ f, skipped: skipped(f) }).toEqual({ f, skipped: true });
    }
    for (const f of [
      'src/pages/dashboard/index.tsx',
      'src/components/LabelBadge.tsx',
      'src/charts/C09/index.tsx',
      'src/i18n/index.ts',
      'src/app/ChartGalleryPage.tsx',
    ]) {
      expect({ f, skipped: skipped(f) }).toEqual({ f, skipped: false });
    }
  });
});

describe('저장소 설정: eslint.config.js 가 src 화면 코드 전체에 규칙을 켠다', () => {
  it.each([
    ['src/pages/dashboard/index.tsx', 2],
    ['src/lib/unitBasis.ts', 2],
    ['src/components/LabelBadge.tsx', 2],
    ['src/pages/r5fe.test.tsx', 2], // 켜져 있되 규칙 기본 예외 파일(DEFAULT_EXCEPT)로 건너뛴다
  ])(
    '%s → local/no-hangul-literal = error',
    async (rel, level) => {
      const eslint = new ESLint({ cwd: join(here, '..') });
      const config = await eslint.calculateConfigForFile(join(here, '..', rel));
      const setting = config.rules?.['local/no-hangul-literal'];
      expect(Array.isArray(setting) ? setting[0] : setting).toBe(level);
    },
    60_000,
  );
});
