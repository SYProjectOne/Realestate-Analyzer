import js from '@eslint/js';
import prettier from 'eslint-config-prettier';
import reactHooks from 'eslint-plugin-react-hooks';
import globals from 'globals';
import tseslint from 'typescript-eslint';
import local from './eslint-rules/index.js';

export default tseslint.config(
  {
    ignores: [
      'dist',
      'coverage',
      'playwright-report',
      'test-results',
      'public/mockServiceWorker.js',
      // 생성물 — 손으로 고치지 않는다
      'src/api/schema.d.ts',
      'src/mocks/handlers.gen.ts',
      'eslint-rules/__fixtures__',
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ['src/**/*.{ts,tsx}'],
    languageOptions: {
      globals: globals.browser,
      // 타입 정보: no-raw-number-render가 식의 타입(number)을 본다
      parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname },
    },
    plugins: { 'react-hooks': reactHooks, local },
    rules: {
      ...reactHooks.configs.recommended.rules,
      // RA WP6 완료 기준: FactCell 밖에서 숫자 렌더 금지 (예외 파일은 규칙 기본값)
      'local/no-raw-number-render': 'error',
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
      '@typescript-eslint/consistent-type-imports': ['error', { fixStyle: 'inline-type-imports' }],
      'no-restricted-imports': [
        'error',
        {
          paths: [
            {
              name: 'react-router-dom',
              message: 'react-router v7: "react-router"에서 import 한다.',
            },
          ],
        },
      ],
    },
  },
  {
    files: ['scripts/**/*.ts', 'eslint-rules/**/*.js', 'tests/**/*.ts', '*.config.{js,ts}'],
    languageOptions: { globals: globals.node },
  },
  prettier,
);
