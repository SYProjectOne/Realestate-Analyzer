// @vitest-environment node
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { RuleTester } from 'eslint';
import tseslint from 'typescript-eslint';
import { afterAll, describe, expect, it } from 'vitest';
import rule, { DEFAULT_EXCEPT, DEFAULT_EXCEPT_CALLS } from './no-raw-number-render.js';

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
const invalid = (code, messageId, filename = file) => ({ code, filename, errors: [{ messageId }] });

ruleTester.run('no-raw-number-render (휴리스틱 모드)', rule, {
  valid: [
    valid('<FactCell fact={row.total} unit="score" />'),
    valid("<span>{t('page.G1.title')}</span>"),
    valid('<span>{name}</span>'),
    valid('<span>{row.name}</span>'),
    valid('<span>{formatWon(price)}</span>'),
    valid('<div className="p-4" aria-valuenow={5} tabIndex={0}>{label}</div>'),
    valid("<span>{cond ? t('a') : null}</span>"),
    valid('<ul>{items.map((i) => <li key={i.id}>{i.name}</li>)}</ul>'),
    valid('<p>   </p>'),
    valid('<span>{`${prefix}-${name}`}</span>'),
    // 예외 파일
    valid('<span>{fact.v}</span>', 'src/components/FactCell.tsx'),
    valid('<span>{fact.v}</span>', 'C:\\repo\\frontend\\src\\components\\FactCellInner.tsx'),
    valid('const o = { label: <b>{count}</b> }', 'src/charts/C06/buildOption.tsx'),
    // 옵션으로 예외 목록을 바꿀 수 있다
    {
      code: '<i>{n}</i>',
      filename: 'src/stories/demo.tsx',
      options: [{ exceptFiles: ['stories'] }],
    },
  ],
  invalid: [
    invalid('<span>{42}</span>', 'rawNumber'),
    invalid('<span>{fact.v}</span>', 'rawNumber'),
    invalid('<span>{row.total.v}</span>', 'rawNumber'),
    invalid('<span>{row?.total?.v}</span>', 'rawNumber'),
    invalid('<span>{count}</span>', 'rawNumber'),
    invalid('<span>{row.price_won}</span>', 'rawNumber'),
    invalid('<span>{row.units}</span>', 'rawNumber'),
    invalid('<span>{x * 100}</span>', 'rawNumber'),
    invalid('<span>{-delta}</span>', 'rawNumber'),
    invalid('<span>{items.length}</span>', 'rawNumber'),
    invalid('<span>{value.toFixed(1)}</span>', 'manualFormat'),
    invalid('<span>{n.toLocaleString()}</span>', 'manualFormat'),
    invalid('<span>{String(fact.v)}</span>', 'rawNumber'),
    invalid('<span>84㎡</span>', 'rawNumberText'),
    invalid('<span>{`${count}건`}</span>', 'rawNumber'),
    invalid('<span>{cond ? fact.v : null}</span>', 'rawNumber'),
    invalid('<>{ready && fact.v}</>', 'rawNumber'),
    invalid('<span>{(fact.v as number)}</span>', 'rawNumber'),
    invalid('<span>{fact.v!}</span>', 'rawNumber'),
    // 예외 목록에 없는 차트 index.tsx는 검사 대상
    invalid('<b>{count}</b>', 'rawNumber', 'src/charts/C06/index.tsx'),
  ],
});

// ─── R3 minor 27: props · i18n 파라미터 · formatNumber(신뢰도) · showLabel={false} ──────────
ruleTester.run('no-raw-number-render (props·i18n·format 확장)', rule, {
  valid: [
    // 화면 글자가 아닌 props(머리말 SAFE_PROPS 근거)
    valid('<div key={row.id} id={count} tabIndex={0} data-rank={rank} aria-valuenow={n} />'),
    valid('<input value={count} maxLength={64} min={0} max={total} step={1} />'),
    valid('<progress max={progress.total} value={progress.done} />'),
    valid('<JobProgress jobId={job.id} pollMs={2000} />'),
    valid('<RawPreview rawId={row.raw_document_id} complex_id={row.complex_id} />'),
    valid('<Link to={`/complexes/${row.complex_id}`} />'),
    valid('<td colSpan={count} rowSpan={2} />'),
    valid('<FactCell fact={row.total} unit="score" />'),
    valid("<Badge title={formatCount(count)} label={t('x', { n: formatCount(count) })} />"),
    valid('<FactCell fact={row.total} showLabel />'),
    valid('<FactCell fact={row.total} showLabel={true} />'),
    // i18n 파라미터: 문자열·식별자
    valid("const s = t('page.G6.flag', { name, n: formatCount(n) });"),
    valid("const s = t('chart.C10.complex', { id: row.complex_id });"),
    valid("const s = t('page.G7.claims.pending', { job: idText(jobId) });"),
    valid('const s = tDynamic(`x.${k}`, k, { n: formatCount(count) });'),
    // formatNumber: 신뢰도·확률이 아닌 값
    valid('const s = formatNumber(weights.p10, 2);'),
    valid('const s = formatConfidence(decision.confidence);'),
    // format.ts 자체·테스트는 호출 검사 예외
    valid("const s = t('unit.dminus', { n: diff });", 'src/lib/format.ts'),
    valid(
      "expect(x).toBe(t('page.G5.error.max', { max: 84 }));",
      'src/pages/scenario/scenario.test.tsx',
    ),
    // 차트 buildOption 은 JSX 검사 예외(속성 포함)
    valid('const o = <b title={count} />', 'src/charts/C06/buildOption.tsx'),
  ],
  invalid: [
    // 화면 글자로 렌더되는 props
    invalid('<span title={count} />', 'rawNumberProp'),
    invalid('<input placeholder={fact.v} />', 'rawNumberProp'),
    invalid('<span aria-label={total} />', 'rawNumberProp'),
    invalid('<Badge label={row.rank} />', 'rawNumberProp'),
    invalid('<EmptyState message={items.length} />', 'rawNumberProp'),
    invalid('<Card subtitle={ready ? fact.v : null} />', 'rawNumberProp'),
    invalid('<Card subtitle={`${count}건`} />', 'rawNumberProp'),
    invalid('<Card subtitle={x * 100} />', 'rawNumberProp'),
    invalid('<Card subtitle={n.toFixed(1)} />', 'manualFormat'),
    // i18n 파라미터의 숫자
    invalid("const s = t('page.G6.flag', { name, n: count });", 'rawNumberParam'),
    invalid("const s = t('badge.sample', { n: list.length - 1 });", 'rawNumberParam'),
    invalid("const s = t('x', { sum: total.toFixed(2) });", 'manualFormat'),
    {
      code: "const s = t('x', { n: ok ? count : 0 });",
      filename: file,
      errors: [{ messageId: 'rawNumberParam' }, { messageId: 'rawNumberParam' }],
    },
    invalid("const s = tDynamic('x', 'y', { n: row.units });", 'rawNumberParam'),
    // 차트 buildOption 의 툴팁·라벨 문자열도 검사한다
    invalid(
      "const s = t('chart.C04.markerMore', { n: list.length });",
      'rawNumberParam',
      'src/charts/C04/buildOption.ts',
    ),
    // 신뢰도·확률을 formatNumber 로
    invalid('const s = formatNumber(confidence, 2);', 'confidenceFormat'),
    invalid('const s = formatNumber(env.confidence, 2);', 'confidenceFormat'),
    invalid('const s = formatNumber(decision.confidence.v, 2);', 'confidenceFormat'),
    invalid('const s = formatNumber(item.p_wrong);', 'confidenceFormat'),
    invalid('const s = formatNumber(row.stage_prob);', 'confidenceFormat'),
    invalid(
      'const s = formatNumber(c.inclusionProb, 2);',
      'confidenceFormat',
      'src/charts/C07/buildOption.ts',
    ),
    // 라벨 숨김
    invalid('<FactCell fact={price.price_low} unit="won" showLabel={false} />', 'hiddenLabel'),
  ],
});

// ─── 타입 모드 (eslint.config.js와 같이 projectService 사용) ───────────────
const fixtures = join(dirname(fileURLToPath(import.meta.url)), '__fixtures__');
const typedTester = new RuleTester({
  languageOptions: {
    parser: tseslint.parser,
    parserOptions: {
      ecmaFeatures: { jsx: true },
      projectService: true,
      tsconfigRootDir: fixtures,
    },
  },
});
const typedFile = join(fixtures, 'file.tsx');
const tv = (code) => ({ code, filename: typedFile });
const ti = (code, messageId = 'rawNumber') => ({
  code,
  filename: typedFile,
  errors: [{ messageId }],
});

typedTester.run('no-raw-number-render (타입 모드)', rule, {
  valid: [
    // 이름이 숫자처럼 보여도 타입이 string이면 허용
    tv('declare const count: string; const el = <span>{count}</span>;'),
    tv('declare const fact: { v: string }; const el = <span>{fact.v}</span>;'),
    tv(
      'declare const f: (n: number) => string; declare const x: number; const el = <span>{f(x)}</span>;',
    ),
    // children: ReactNode 같은 "렌더 가능한 무엇이든" 슬롯(객체 타입 포함 유니온)은 허용
    tv(
      'type Node = { type: string } | string | number | null; declare const children: Node; const el = <div>{children}</div>;',
    ),
  ],
  invalid: [
    // 이름과 무관하게 타입이 number면 금지
    ti('declare const foo: number; const el = <span>{foo}</span>;'),
    ti('declare const fact: { v: number | string | null }; const el = <span>{fact.v}</span>;'),
    ti('declare const r: { rank: number }; const el = <span>{r.rank}</span>;'),
    ti(
      'declare const xs: string[]; declare const ok: boolean; const el = <span>{ok && xs.length}</span>;',
    ),
  ],
});

// 타입 모드 props: 받는 쪽 prop 타입이 숫자뿐이면 허용, ReactNode·string 슬롯이면 금지
const COMP =
  'type Node = { type: string } | string | number | null; ' +
  'declare function Comp(p: { conf?: number | null; total: number; label?: Node; text?: string | number }): Node; ';
typedTester.run('no-raw-number-render (타입 모드 props)', rule, {
  valid: [
    tv(`${COMP} declare const c: number; const el = <Comp total={c} conf={c} />;`),
    tv(`${COMP} declare const s: string; const el = <Comp total={1} label={s} />;`),
  ],
  invalid: [
    ti(
      `${COMP} declare const c: number; const el = <Comp total={1} label={c} />;`,
      'rawNumberProp',
    ),
    ti(`${COMP} declare const c: number; const el = <Comp total={1} text={c} />;`, 'rawNumberProp'),
  ],
});

describe('기본 예외 파일', () => {
  const matches = (path) => DEFAULT_EXCEPT.some((source) => new RegExp(source).test(path));
  it('FactCell*, lib/format.ts, charts/**/buildOption.ts는 예외', () => {
    expect(matches('src/components/FactCell.tsx')).toBe(true);
    expect(matches('C:\\x\\frontend\\src\\lib\\format.ts')).toBe(true);
    expect(matches('/x/frontend/src/charts/C01/buildOption.ts')).toBe(true);
  });
  it('호출 검사(i18n 파라미터·formatNumber) 예외는 format.ts·테스트뿐 — buildOption 은 검사', () => {
    const callExcept = (path) => DEFAULT_EXCEPT_CALLS.some((s) => new RegExp(s).test(path));
    expect(callExcept('C:\\x\\frontend\\src\\lib\\format.ts')).toBe(true);
    expect(callExcept('src/pages/ops/ops.test.tsx')).toBe(true);
    expect(callExcept('/x/frontend/src/charts/C01/buildOption.ts')).toBe(false);
    expect(callExcept('src/components/FactCell.tsx')).toBe(false);
  });
  it('그 밖은 검사 대상', () => {
    expect(matches('src/components/LabelBadge.tsx')).toBe(false);
    expect(matches('src/lib/format.test.ts')).toBe(false);
    expect(matches('src/charts/C01/index.tsx')).toBe(false);
  });
});
