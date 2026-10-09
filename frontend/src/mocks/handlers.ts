import { extraHandlers } from './handlers.extra';
import { generatedHandlers } from './handlers.gen';

/** 수동 보강이 생성물보다 먼저 매칭된다. 테스트는 server.use(...)로 개별 덮어쓴다. */
export const handlers = [...extraHandlers, ...generatedHandlers];
