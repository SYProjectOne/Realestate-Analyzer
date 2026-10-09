/** 로컬 ESLint 플러그인 — eslint.config.js에서 `local/<rule>`로 쓴다. */
import noRawNumberRender from './no-raw-number-render.js';

export default {
  meta: { name: 'eslint-plugin-local' },
  rules: {
    'no-raw-number-render': noRawNumberRender,
  },
};
