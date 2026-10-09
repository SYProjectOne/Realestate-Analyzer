import { expect, type APIRequestContext, type Page, type Response } from '@playwright/test';
import { API, AUTH } from '../env';

/** 화면이 부른 /api 응답 중 4xx/5xx (계약 위반·출처 누락 500 포함) */
export function watchApi(page: Page): string[] {
  const failed: string[] = [];
  page.on('response', (r: Response) => {
    const url = new URL(r.url());
    if (url.pathname.startsWith('/api/') && r.status() >= 400) {
      failed.push(`${r.status()} ${r.request().method()} ${url.pathname}${url.search}`);
    }
  });
  return failed;
}

export async function ready(page: Page, path: string, title: string): Promise<void> {
  await page.goto(path);
  await expect(page.getByRole('heading', { level: 1, name: title })).toBeVisible();
}

/** 백엔드 API 직접 조회(화면과 같은 토큰) */
export async function apiGet<T>(request: APIRequestContext, path: string): Promise<T> {
  const r = await request.get(`${API}/api${path}`, { headers: AUTH });
  expect(r.status(), `GET ${path}: ${await r.text()}`).toBe(200);
  return (await r.json()) as T;
}

export interface Top5Row {
  complex_id: number;
  name: string;
  rank: number | null;
  intake?: { status: string; path: string } | null;
}
