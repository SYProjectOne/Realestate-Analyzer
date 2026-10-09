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
 *
 * R3 minor 27 확장:
 *  5. JSX 속성(props)으로 넘기는 숫자 식도 검사한다(`title={count}`, `label={fact.v}`, `<Badge text={n}>` …).
 *     예외(SAFE_PROPS — 화면 글자로 렌더되지 않는 값):
 *       - FactCell 의 fact(숫자가 가야 할 자리)
 *       - React/DOM 구조: key·id·ref·tabIndex·className·style·htmlFor·name·role·type
 *       - 주소: to·href·src (URL 안의 id 는 표시 숫자가 아니다)
 *       - data-* 전부, aria-* (단 글자로 읽히는 aria-label·aria-valuetext·aria-description·aria-roledescription 은 검사)
 *       - 크기·범위·입력 제약: width·height·min·max·step·rows·cols·size·span·colSpan·rowSpan·start·maxLength·minLength
 *         ·x·y·cx·cy·r·strokeWidth·opacity·zIndex
 *       - 폼 컨트롤 값: value·defaultValue(입력 칸·progress 는 원값을 편집·표시해야 한다 — 포맷하면 파싱이 깨진다)
 *       - 이름 규칙: *Id·*Ids·*_id·*Index·*Ms·*Px, index·dataIndex·seriesIndex·delay·duration·timeout·digits·page·size
 *         (식별자·시간·자릿수 — 표시 숫자가 아님)
 *       - 타입 모드에서 받는 쪽 prop 타입이 숫자뿐(number | null | undefined)이면 허용 — 그 컴포넌트가 포맷하고
 *         그 컴포넌트의 렌더도 이 규칙이 검사한다. ReactNode·string 이 섞인 슬롯으로 숫자를 넘기면 금지.
 *  6. i18n `t(key, { p: <숫자> })`·`tDynamic(key, fallback, { … })` 파라미터의 숫자 식 금지 — formatCount 등으로
 *     문자열을 만들어 넘긴다(t 는 String(n) 으로 끼워 넣어 천 단위·단위가 빠진다). 파라미터 이름이 id·*Id·*_id 면 허용.
 *  7. `formatNumber(<신뢰도·확률 같은 값>)` 금지 — confidence·prob 은 FactCell(Fact) 또는 formatConfidence·formatProb.
 *  8. `<FactCell showLabel={false}>` 금지 — 라벨은 항상 보인다(AGENTS 규칙 5).
 *
 * 예외 파일(기본, 1~5·8): src/components/FactCell*, src/lib/format.ts, src/charts/**\/buildOption.ts
 * 예외 파일(6·7 — 호출 검사): src/lib/format.ts(포맷 구현)·*.test.* 만. buildOption.ts 의 툴팁·라벨 문자열도 검사한다.
 * 옵션 { exceptFiles: string[], exceptCallFiles: string[] } (정규식 소스)로 바꿀 수 있다.
 */

import ts from 'typescript';

export const DEFAULT_EXCEPT = [
  String.raw`(^|[\\/])src[\\/]components[\\/]FactCell[^\\/]*$`,
  String.raw`(^|[\\/])src[\\/]lib[\\/]format\.ts$`,
  String.raw`(^|[\\/])src[\\/]charts[\\/](.+[\\/])?buildOption\.tsx?$`,
];

/** 6·7(호출 검사) 예외 — 포맷 구현 자체 */
export const DEFAULT_EXCEPT_CALLS = [
  String.raw`(^|[\\/])src[\\/]lib[\\/]format\.ts$`,
  // 테스트는 기대 문자열을 만들 뿐 화면에 렌더하지 않는다
  String.raw`\.test\.[jt]sx?$`,
];

/** 5: 화면 글자로 렌더되지 않는 props(위 머리말의 근거) */
const SAFE_PROPS = new Set([
  // FactCell 의 fact — 숫자가 가야 할 바로 그 자리(라벨·출처와 함께 포맷)
  'fact',
  'key',
  'id',
  'ref',
  'tabIndex',
  'className',
  'style',
  'htmlFor',
  'name',
  'role',
  'type',
  'to',
  'href',
  'src',
  'width',
  'height',
  'min',
  'max',
  'step',
  'rows',
  'cols',
  'size',
  'span',
  'colSpan',
  'rowSpan',
  'start',
  'maxLength',
  'minLength',
  'x',
  'y',
  'cx',
  'cy',
  'r',
  'strokeWidth',
  'opacity',
  'zIndex',
  'value',
  'defaultValue',
  'index',
  'dataIndex',
  'seriesIndex',
  'delay',
  'duration',
  'timeout',
  'digits',
  'page',
]);
/** aria-* 중 글자로 읽히는 것(검사 대상) */
const TEXT_ARIA = new Set([
  'aria-label',
  'aria-valuetext',
  'aria-description',
  'aria-roledescription',
  'aria-placeholder',
]);
const SAFE_PROP_NAME = /(Id|Ids|_id|_ids|Index|Ms|Px)$/;

function isSafeProp(name) {
  if (SAFE_PROPS.has(name)) return true;
  if (name.startsWith('data-')) return true;
  if (name.startsWith('aria-')) return !TEXT_ARIA.has(name);
  return SAFE_PROP_NAME.test(name);
}

/** 7: 신뢰도·확률 같은 이름(formatNumber 로 포맷 금지) */
const CONFIDENCE_NAME =
  /^(confidence|conf|prob|probability|p_wrong|pWrong)$|(_prob|_confidence|Prob|Confidence)$/;

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
        properties: {
          exceptFiles: { type: 'array', items: { type: 'string' } },
          exceptCallFiles: { type: 'array', items: { type: 'string' } },
        },
        additionalProperties: false,
      },
    ],
    messages: {
      rawNumber:
        '숫자는 <FactCell>(라벨·출처) 또는 src/lib/format.ts 포맷 함수로만 렌더한다 (no-raw-number-render).',
      rawNumberText:
        'JSX 텍스트에 숫자를 직접 쓰지 않는다 — 문구는 ko.json, 숫자는 FactCell/format.',
      manualFormat: 'toFixed/toLocaleString 같은 수동 포맷 금지 — src/lib/format.ts 함수를 쓴다.',
      rawNumberProp:
        'JSX 속성으로 숫자를 넘기지 않는다 — FactCell 또는 src/lib/format.ts 로 만든 문자열을 넘긴다 (no-raw-number-render).',
      rawNumberParam:
        'i18n t() 파라미터에 숫자를 넣지 않는다 — formatCount·formatScore 등으로 만든 문자열을 넣는다.',
      confidenceFormat:
        '신뢰도·확률은 formatNumber 로 포맷하지 않는다 — FactCell(Fact) 또는 formatConfidence·formatProb 를 쓴다.',
      hiddenLabel:
        'FactCell 라벨을 숨기지 않는다(showLabel={false} 금지) — 모든 수치는 라벨과 함께 보인다.',
    },
  },

  create(context) {
    const options = context.options[0] ?? {};
    const patterns = (options.exceptFiles ?? DEFAULT_EXCEPT).map((source) => new RegExp(source));
    const callPatterns = (options.exceptCallFiles ?? DEFAULT_EXCEPT_CALLS).map(
      (source) => new RegExp(source),
    );
    const filename = context.filename ?? context.getFilename();
    const skipJsx = patterns.some((re) => re.test(filename));
    const skipCalls = callPatterns.some((re) => re.test(filename));
    if (skipJsx && skipCalls) return {};

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

    /** 타입 모드: 받는 쪽(prop) 타입이 숫자뿐인가(number | null | undefined) */
    function contextualNumberOnly(node) {
      if (!checker) return false;
      let tsNode;
      try {
        tsNode = services.esTreeNodeToTSNodeMap.get(node);
      } catch {
        return false;
      }
      if (!tsNode) return false;
      const type = checker.getContextualType(tsNode);
      if (!type) return false;
      if (type.getFlags() & (ts.TypeFlags.Any | ts.TypeFlags.Unknown)) return false;
      const parts = type.isUnion() ? type.types : [type];
      const allowed =
        ts.TypeFlags.NumberLike |
        ts.TypeFlags.BigIntLike |
        ts.TypeFlags.Null |
        ts.TypeFlags.Undefined |
        ts.TypeFlags.Void;
      return (
        parts.some((p) => (p.getFlags() & ts.TypeFlags.NumberLike) !== 0) &&
        parts.every((p) => (p.getFlags() & allowed) !== 0)
      );
    }

    /** 5: 속성 값 식 검사(조건·논리 양쪽, 템플릿 안쪽). 함수·객체·배열·JSX 는 건너뛴다 */
    function checkProp(node, report) {
      const expr = unwrap(node);
      if (!expr) return;
      switch (expr.type) {
        case 'ConditionalExpression':
          checkProp(expr.consequent, report);
          checkProp(expr.alternate, report);
          return;
        case 'LogicalExpression':
          checkProp(expr.left, report);
          checkProp(expr.right, report);
          return;
        case 'TemplateLiteral':
          for (const inner of expr.expressions) {
            if (isManualFormat(inner)) context.report({ node: inner, messageId: 'manualFormat' });
            else if (isNumeric(inner)) report(inner);
          }
          return;
        case 'JSXElement':
        case 'JSXFragment':
        case 'ArrowFunctionExpression':
        case 'FunctionExpression':
        case 'ObjectExpression':
        case 'ArrayExpression':
          return;
        default:
          if (isManualFormat(expr)) context.report({ node: expr, messageId: 'manualFormat' });
          else if (isNumeric(expr)) report(expr);
      }
    }

    function attrName(attr) {
      const n = attr.name;
      if (n.type === 'JSXIdentifier') return n.name;
      if (n.type === 'JSXNamespacedName') return `${n.namespace.name}:${n.name.name}`;
      return null;
    }

    function elementName(opening) {
      const n = opening?.name;
      if (!n) return null;
      if (n.type === 'JSXIdentifier') return n.name;
      if (n.type === 'JSXMemberExpression') return n.property.name;
      return null;
    }

    /** 6: t(key, {…})·tDynamic(key, fallback, {…}) 의 파라미터 객체 */
    function i18nParams(node) {
      const callee = unwrap(node.callee);
      const name =
        callee?.type === 'Identifier'
          ? callee.name
          : callee?.type === 'MemberExpression'
            ? propertyName(callee)
            : null;
      if (name === 't') return node.arguments[1] ?? null;
      if (name === 'tDynamic') return node.arguments[2] ?? null;
      return null;
    }

    function checkParams(arg) {
      const obj = unwrap(arg);
      if (!obj) return;
      if (obj.type === 'ObjectExpression') {
        for (const prop of obj.properties) {
          if (prop.type !== 'Property') continue;
          // {id}·{complexId} 같은 식별자 파라미터는 표시 숫자가 아니다
          const key = prop.key.type === 'Identifier' ? prop.key.name : null;
          if (key && (key === 'id' || SAFE_PROP_NAME.test(key))) continue;
          const value = unwrap(prop.value);
          if (!value) continue;
          if (value.type === 'ConditionalExpression') {
            for (const branch of [value.consequent, value.alternate]) {
              if (isNumeric(branch)) context.report({ node: branch, messageId: 'rawNumberParam' });
            }
          } else if (isManualFormat(value)) {
            context.report({ node: value, messageId: 'manualFormat' });
          } else if (isNumeric(value)) {
            context.report({ node: value, messageId: 'rawNumberParam' });
          }
        }
      }
    }

    function argName(node) {
      const expr = unwrap(node);
      if (!expr) return null;
      if (expr.type === 'Identifier') return expr.name;
      if (expr.type === 'MemberExpression') {
        const name = propertyName(expr);
        // fact.v → 그 Fact 의 이름(confidence.v)
        if (name === 'v') return argName(expr.object);
        return name;
      }
      if (expr.type === 'LogicalExpression') return argName(expr.left);
      return null;
    }

    const visitors = {};
    if (!skipJsx) {
      visitors.JSXExpressionContainer = (node) => {
        if (!isChildPosition(node)) return;
        if (node.expression.type === 'JSXEmptyExpression') return;
        check(node.expression);
      };
      visitors.JSXText = (node) => {
        if (!isChildPosition(node)) return;
        if (/\d/.test(node.value)) context.report({ node, messageId: 'rawNumberText' });
      };
      visitors.JSXAttribute = (node) => {
        const name = attrName(node);
        if (name === null) return;
        const value = node.value;
        if (
          name === 'showLabel' &&
          elementName(node.parent) === 'FactCell' &&
          value?.type === 'JSXExpressionContainer' &&
          value.expression.type === 'Literal' &&
          value.expression.value === false
        ) {
          context.report({ node, messageId: 'hiddenLabel' });
          return;
        }
        if (!value || value.type !== 'JSXExpressionContainer') return;
        if (value.expression.type === 'JSXEmptyExpression') return;
        if (isSafeProp(name)) return;
        if (contextualNumberOnly(value.expression)) return;
        checkProp(value.expression, (n) => context.report({ node: n, messageId: 'rawNumberProp' }));
      };
    }
    if (!skipCalls) {
      visitors.CallExpression = (node) => {
        const params = i18nParams(node);
        if (params) checkParams(params);
        const callee = unwrap(node.callee);
        if (callee?.type === 'Identifier' && callee.name === 'formatNumber') {
          const name = argName(node.arguments[0]);
          if (name && CONFIDENCE_NAME.test(name)) {
            context.report({ node, messageId: 'confidenceFormat' });
          }
        }
      };
    }
    return visitors;
  },
};

export default rule;
