// @vitest-environment node
import { RuleTester } from 'eslint';
import tseslint from 'typescript-eslint';
import { afterAll, describe, it } from 'vitest';
import rule from './no-raw-number-render.js';

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
    valid('const o = { label: <b>{count}</b> }', 'src/charts/C06/buildOption.ts'),
    valid('const x = <i>{n}</i>', 'src/lib/format.ts'),
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
  ],
});
