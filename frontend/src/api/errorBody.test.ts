/**
 * R5-FE2: 계약 `Error` 본문 판별(`parseErrorBody`)을 zod 없이 한다 — 첫 화면 진입 청크에서 zod(~50kB min)를 뺀다.
 * zod 스키마(`z.object({ code: z.enum(API_ERROR_CODES), detail: z.string(), field_errors: …nullish(), request_id: …nullish() })`)
 * 와 같은 판정을 고정한다.
 */
import { parseErrorBody, toApiError } from './client';
import { API_ERROR_CODES } from './types';

describe('parseErrorBody — 계약 Error 본문', () => {
  it('code·detail 만 있으면 통과(field_errors 는 빈 배열)', () => {
    expect(parseErrorBody({ code: 'not_found', detail: '없음' })).toEqual({
      code: 'not_found',
      detail: '없음',
      fieldErrors: [],
    });
  });

  it('계약 code 전부를 받는다', () => {
    for (const code of API_ERROR_CODES) {
      expect(parseErrorBody({ code, detail: 'x' })?.code).toBe(code);
    }
  });

  it('field_errors·request_id(null 포함)를 받고, field_errors 항목은 loc·msg 만 남긴다', () => {
    expect(
      parseErrorBody({
        code: 'validation_error',
        detail: 'bad',
        field_errors: [{ loc: ['body', 'name', 0], msg: '필수', type: 'missing' }],
        request_id: 'r-1',
        extra: 1,
      }),
    ).toEqual({
      code: 'validation_error',
      detail: 'bad',
      fieldErrors: [{ loc: ['body', 'name', 0], msg: '필수' }],
    });
    expect(
      parseErrorBody({ code: 'conflict', detail: 'c', field_errors: null, request_id: null }),
    ).toEqual({ code: 'conflict', detail: 'c', fieldErrors: [] });
  });

  it.each([
    ['null', null],
    ['문자열', 'oops'],
    ['배열', [{ code: 'not_found', detail: 'x' }]],
    ['code 가 계약 밖', { code: 'teapot', detail: 'x' }],
    ['code 없음', { detail: 'x' }],
    ['detail 이 문자열 아님', { code: 'not_found', detail: 3 }],
    ['detail 없음', { code: 'not_found' }],
    ['field_errors 가 배열 아님', { code: 'not_found', detail: 'x', field_errors: {} }],
    [
      'field_errors 항목 loc 원소가 불리언',
      { code: 'not_found', detail: 'x', field_errors: [{ loc: [true], msg: 'm' }] },
    ],
    [
      'field_errors 항목 msg 없음',
      { code: 'not_found', detail: 'x', field_errors: [{ loc: ['a'] }] },
    ],
    ['field_errors 항목이 null', { code: 'not_found', detail: 'x', field_errors: [null] }],
    ['request_id 가 숫자', { code: 'not_found', detail: 'x', request_id: 7 }],
  ])('계약 Error 가 아니면 null — %s', (_name, body) => {
    expect(parseErrorBody(body)).toBeNull();
  });

  it('toApiError: 계약 본문이 아니면 code http 로 떨어진다', async () => {
    const err = await toApiError(
      new Response(JSON.stringify({ code: 'teapot', detail: 'x' }), {
        status: 418,
        statusText: "I'm a teapot",
      }),
    );
    expect(err.code).toBe('http');
    expect(err.status).toBe(418);
    const ok = await toApiError(
      new Response(
        JSON.stringify({
          code: 'validation_error',
          detail: 'bad',
          field_errors: [{ loc: ['body', 'x'], msg: 'm' }],
        }),
        { status: 422 },
      ),
    );
    expect(ok.code).toBe('validation_error');
    expect(ok.fieldErrors).toEqual([{ loc: ['body', 'x'], msg: 'm' }]);
  });
});
