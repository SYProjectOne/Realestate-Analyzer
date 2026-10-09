/**
 * 흐름 (c) G8 보고서 생성(PDF) → 다운로드 — RA §9 T15 / DECISIONS D4.
 * 화면: 기준 스냅샷(최신 2026-10-08) + 비교 스냅샷(2026-10-07) + PDF → 생성(POST 202) → 작업 진행 →
 * worker(`python -m app.worker --once`) → 목록 '완료' → 파일 버튼(Bearer fetch) 다운로드 → PDF 본문 검사.
 */
import { expect, test } from '@playwright/test';
import ko from '../../frontend/src/i18n/ko.json' with { type: 'json' };
import { runWorkerOnce } from '../env';
import { ready, watchApi } from './_util';

const P = ko.page;

test('G8 보고서 PDF: 생성 → worker → 목록 완료 → 다운로드(%PDF, 페이지 > 0)', async ({ page }) => {
  const failed = watchApi(page);
  await ready(page, '/reports?region=1', P.G8.title);
  await page.getByLabel(P.G8.compareSnapshot).selectOption({ label: '2026-10-07' });
  await page.getByRole('radio', { name: P.G8.formats.pdf }).check();
  const created = page.waitForResponse(
    (r) => r.url().endsWith('/api/reports') && r.request().method() === 'POST',
  );
  const generate = page.getByRole('button', { name: P.G8.generate });
  await expect(generate).toBeEnabled();
  await generate.click();
  const post = await created;
  expect(post.status()).toBe(202);
  expect(post.request().postDataJSON()).toMatchObject({ format: 'pdf', compare_snapshot_id: 11 });
  await expect(page.getByText(ko.job.title)).toBeVisible();

  runWorkerOnce();

  const list = page.getByRole('table', { name: P.G8.list });
  const fileButton = list.getByRole('button', { name: /^report_.*\.pdf$/ }).first();
  await expect(fileButton).toBeVisible({ timeout: 60_000 });
  const [download] = await Promise.all([page.waitForEvent('download'), fileButton.click()]);
  expect(download.suggestedFilename()).toMatch(/^report_.*\.pdf$/);
  const { readFile } = await import('node:fs/promises');
  const pdf = await readFile(await download.path());
  expect(pdf.subarray(0, 5).toString('latin1')).toBe('%PDF-');
  const pages = pdf.toString('latin1').match(/\/Type\s*\/Page[^s]/g) ?? [];
  expect(pages.length).toBeGreaterThan(0);
  expect(failed).toEqual([]);
});
