/**
 * no-raw-number-render — "FactCell 밖에서 숫자 렌더 금지" (RA WP6 완료 기준, AGENTS 규칙 12).
 *
 * JSX 자식으로 숫자가 그대로 렌더되는 것을 막는다. 숫자는 <FactCell>(라벨·출처 포함) 또는
 * src/lib/format.ts의 포맷 함수(문자열 반환)를 거쳐야 한다.
 *
 * 판정 방식(합리적 휴리스틱):
 *  1. 타입 정보가 있으면(parserOptions.projectService) 식의 타입이 number/bigint(유니온 포함)인지 본다.
 *     any/unknown이면 2로 넘어간다.
 *  2. 타입 정보가 없으면 구문으로 본다: 숫자 리터럴, `.v` 접근, 산술 연산, 단항 +/-, `.length`,
 *     숫자를 암시하는 이름(count·total·price·*_won·units …), String()/Number()로 감싼 숫자.
 *  3. 어느 모드든 JSX 안의 `.toFixed()`·`.toLocaleString()`·`.toPrecision()`은 수동 포맷으로 금지.
 *  4. JSX 텍스트에 숫자가 있으면 금지(문자열은 ko.json, 숫자는 FactCell).
 * 속성(attribute) 값은 검사하지 않는다(`tabIndex={0}`, `aria-valuenow={n}` 허용).
 *
 * 예외 파일(기본): src/components/FactCell*, src/lib/format.ts, src/charts/**\/buildOption.ts
 * 옵션 { exceptFiles: string[] } (정규식 소스)로 바꿀 수 있다.
 */

import ts from 'typescript';

export const DEFAULT_EXCEPT = [
  String.raw`(^|[\\/])src[\\/]components[\\/]FactCell[^\\/]*$`,
  String.raw`(^|[\\/])src[\\/]lib[\\/]format\.ts$`,
  String.raw`(^|[\\/])src[\\/]charts[\\/](.+[\\/])?buildOption\.tsx?$`,
];

const MANUAL_FORMAT_METHODS = new Set([
  'toFixed',
  'toLocaleString',
  'toPrecision',
  'toExponential',
]);
const ARITHMETIC = new Set(['-', '*', '/', '%', '**', '|', '&', '^', '<<', '>>', '>>>']);

/** 숫자를 암시하는 이름 — 정확 일치 또는 접미사 */
const NUMERIC_NAME_EXACT =
  /^(n|num|count|cnt|total|sum|amount|price|won|ratio|pct|percent|prob|probability|score|rank|units|area|m2|households|length|qty|delta|diff|index|idx)$/i;
const NUMERIC_NAME_SUFFIX =
  /(_won|_m2|_pct|_count|_total|_ratio|_prob|_score|_units|_rank|_amount|_price|Won|Count|Total|Pct|Ratio|Prob|Score|Units|Rank|Amount|Price)$/;

function isNumericName(name) {
  return NUMERIC_NAME_EXACT.test(name) || NUMERIC_NAME_SUFFIX.test(name);
}

function unwrap(node) {
  let current = node;
  while (
    current &&
    (current.type === 'ChainExpression' ||
      current.type === 'TSNonNullExpression' ||
      current.type === 'TSAsExpression' ||
      current.type === 'TSSatisfiesExpression' ||
      current.type === 'TSTypeAssertion')
  ) {
    current = current.expression;
  }
  return current;
}

function propertyName(member) {
  if (member.computed) return null;
  return member.property.type === 'Identifier' ? member.property.name : null;
}

/** @type {import('eslint').Rule.RuleModule} */
const rule = {
  meta: {
    type: 'problem',
    docs: {
      description: 'JSX에서 숫자를 직접 렌더하지 않는다 — FactCell 또는 src/lib/format.ts를 쓴다',
    },
    schema: [
      {
        type: 'object',
        properties: { exceptFiles: { type: 'array', items: { type: 'string' } } },
        additionalProperties: false,
      },
    ],
    messages: {
      rawNumber:
        '숫자는 <FactCell>(라벨·출처) 또는 src/lib/format.ts 포맷 함수로만 렌더한다 (no-raw-number-render).',
      rawNumberText:
        'JSX 텍스트에 숫자를 직접 쓰지 않는다 — 문구는 ko.json, 숫자는 FactCell/format.',
      manualFormat: 'toFixed/toLocaleString 같은 수동 포맷 금지 — src/lib/format.ts 함수를 쓴다.',
    },
  },

  create(context) {
    const options = context.options[0] ?? {};
    const patterns = (options.exceptFiles ?? DEFAULT_EXCEPT).map((source) => new RegExp(source));
    const filename = context.filename ?? context.getFilename();
    if (patterns.some((re) => re.test(filename))) return {};

    const services = context.sourceCode?.parserServices ?? context.parserServices;
    const typed = Boolean(services?.program && services?.esTreeNodeToTSNodeMap);
    const checker = typed ? services.program.getTypeChecker() : null;

    /** 타입 기반: true(숫자) | false(숫자 아님) | null(판단 불가 → 휴리스틱) */
    function typeSaysNumeric(node) {
      if (!checker) return null;
      let tsNode;
      try {
        tsNode = services.esTreeNodeToTSNodeMap.get(node);
      } catch {
        return null;
      }
      if (!tsNode) return null;
      const type = checker.getTypeAtLocation(tsNode);
      if (type.getFlags() & (ts.TypeFlags.Any | ts.TypeFlags.Unknown | ts.TypeFlags.TypeParameter))
        return null;
      const parts = type.isUnion() ? type.types : [type];
      const numeric = ts.TypeFlags.NumberLike | ts.TypeFlags.BigIntLike;
      // ReactNode(children 등)처럼 객체 타입이 섞인 "렌더 가능한 무엇이든" 슬롯은 숫자로 보지 않는다.
      // `number | string | null`(Fact.v)처럼 원시 타입만의 유니온에 number가 있으면 숫자다.
      const objectish = ts.TypeFlags.Object | ts.TypeFlags.NonPrimitive | ts.TypeFlags.Intersection;
      if (parts.some((part) => (part.getFlags() & objectish) !== 0)) return false;
      return parts.some((part) => (part.getFlags() & numeric) !== 0);
    }

    function isManualFormat(node) {
      const expr = unwrap(node);
      if (expr?.type !== 'CallExpression') return false;
      const callee = unwrap(expr.callee);
      return (
        callee?.type === 'MemberExpression' && MANUAL_FORMAT_METHODS.has(propertyName(callee) ?? '')
      );
    }

    function heuristicNumeric(node) {
      const expr = unwrap(node);
      if (!expr) return false;
      switch (expr.type) {
        case 'Literal':
          return typeof expr.value === 'number' || typeof expr.value === 'bigint';
        case 'UnaryExpression':
          return expr.operator === '-' || expr.operator === '+' || expr.operator === '~';
        case 'UpdateExpression':
          return true;
        case 'BinaryExpression':
          if (ARITHMETIC.has(expr.operator)) return true;
          if (expr.operator === '+') return isNumeric(expr.left) || isNumeric(expr.right);
          return false;
        case 'Identifier':
          return isNumericName(expr.name);
        case 'MemberExpression': {
          const name = propertyName(expr);
          if (name === null) return false;
          return name === 'v' || isNumericName(name);
        }
        case 'CallExpression': {
          const callee = unwrap(expr.callee);
          if (
            callee?.type === 'Identifier' &&
            (callee.name === 'String' || callee.name === 'Number')
          ) {
            return expr.arguments.length > 0 && isNumeric(expr.arguments[0]);
          }
          if (
            callee?.type === 'MemberExpression' &&
            callee.object.type === 'Identifier' &&
            callee.object.name === 'Math'
          ) {
            return true;
          }
          return false;
        }
        default:
          return false;
      }
    }

    function isNumeric(node) {
      const expr = unwrap(node);
      if (!expr) return false;
      // String(x)/Number(x) 감싸기는 타입이 string이어도 안의 숫자를 본다
      if (expr.type === 'CallExpression') {
        const callee = unwrap(expr.callee);
        if (
          callee?.type === 'Identifier' &&
          (callee.name === 'String' || callee.name === 'Number')
        ) {
          return expr.arguments.length > 0 && isNumeric(expr.arguments[0]);
        }
      }
      const byType = typeSaysNumeric(expr);
      if (byType !== null) return byType;
      return heuristicNumeric(expr);
    }

    /** JSX 자식으로 렌더되는 식을 검사 */
    function check(node) {
      const expr = unwrap(node);
      if (!expr) return;
      switch (expr.type) {
        case 'ConditionalExpression':
          check(expr.consequent);
          check(expr.alternate);
          return;
        case 'LogicalExpression':
          // `a && b`에서 a가 0이면 0이 렌더된다 → 양쪽 다 검사
          check(expr.left);
          check(expr.right);
          return;
        case 'TemplateLiteral':
          for (const inner of expr.expressions) {
            if (isManualFormat(inner)) context.report({ node: inner, messageId: 'manualFormat' });
            else if (isNumeric(inner)) context.report({ node: inner, messageId: 'rawNumber' });
          }
          return;
        case 'JSXElement':
        case 'JSXFragment':
        case 'ArrowFunctionExpression':
        case 'FunctionExpression':
          return;
        default:
          if (isManualFormat(expr)) context.report({ node: expr, messageId: 'manualFormat' });
          else if (isNumeric(expr)) context.report({ node: expr, messageId: 'rawNumber' });
      }
    }

    const isChildPosition = (node) =>
      node.parent?.type === 'JSXElement' || node.parent?.type === 'JSXFragment';

    return {
      JSXExpressionContainer(node) {
        if (!isChildPosition(node)) return;
        if (node.expression.type === 'JSXEmptyExpression') return;
        check(node.expression);
      },
      JSXText(node) {
        if (!isChildPosition(node)) return;
        if (/\d/.test(node.value)) context.report({ node, messageId: 'rawNumberText' });
      },
    };
  },
};

export default rule;
