import { setupWorker } from 'msw/browser';
import { handlers } from './handlers';

/** 브라우저(dev:msw, Playwright) — main.tsx가 MSW 모드일 때만 동적 import 한다. */
export const worker = setupWorker(...handlers);
