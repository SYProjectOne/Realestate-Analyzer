import { setupServer } from 'msw/node';
import { handlers } from './handlers';

/** Node(vitest) — src/test/setup.ts가 listen/reset/close 한다. */
export const server = setupServer(...handlers);
