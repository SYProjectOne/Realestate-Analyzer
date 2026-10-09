/**
 * 수동 보강 핸들러 — 생성물(handlers.gen.ts)에 없거나 예시만으로 부족한 동작.
 * 여기 핸들러가 생성 핸들러보다 **먼저** 매칭된다(handlers.ts 순서).
 * 계약에 예시가 생기면 여기서 지운다. 지역명은 목 데이터에만 쓴다.
 */
import { http, HttpResponse } from 'msw';
import type { JobRun } from '@/api/types';
import { mswPath } from './mswPath';

const now = () => new Date().toISOString();

export const extraHandlers = [
  // POST /jobs (202) — 계약 예시가 오기 전 임시
  http.post(mswPath('/jobs'), async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as {
      job_name?: string;
      payload?: Record<string, unknown>;
    };
    const job: JobRun = {
      id: 'job_mock_1',
      job_name: body.job_name ?? 'rejudge',
      kind: 'manual',
      payload: body.payload ?? {},
      scheduled_at: now(),
      started_at: null,
      finished_at: null,
      status: 'queued',
      stats: null,
      error_text: null,
    };
    return HttpResponse.json(job, { status: 202 });
  }),
];
