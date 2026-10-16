// @vitest-environment node
/** R11-I18N: 화면 글자 속 ko.json 키 노출 찾기(scripts/lib/raw-keys.ts — Lighthouse 사전 점검·e2e 가 쓴다) */
import { describe, expect, it } from 'vitest';
import ko from '../src/i18n/ko.json' with { type: 'json' };
import { rawKeysIn } from './lib/raw-keys';

describe('rawKeysIn', () => {
  it('잎 키·한글 잎의 앞부분(하위 트리)을 찾는다', () => {
    expect(rawKeysIn(`제목 page.G3.title 끝`)).toEqual(['page.G3.title']);
    expect(rawKeysIn('chart.C08.kind.본청약')).toEqual(['chart.C08.kind']);
  });

  it('번역된 글자·키가 아닌 점 문자열은 무시', () => {
    expect(rawKeysIn(`${ko.page.G3.title} ${ko.app.disclaimer} v1.2 example.com a.b`)).toEqual([]);
  });
});
