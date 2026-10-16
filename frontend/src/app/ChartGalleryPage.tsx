import { lazy, Suspense } from 'react';
import { loadAllNamespaces, t } from '@/i18n';

/**
 * `/__charts` (dev 전용, routes.tsx가 DEV·MSW 모드에서만 등록) — WP6b의 `@/charts/gallery`.
 * 예시 JSON 번들이라 지연 로드한다. 제목(h1)은 갤러리가 갖는다.
 * R11-I18N: 화면이 아니라 화면 청크 문자열이 없다 — 이름공간(차트·용어·화면 예시 문구)을 전부 함께 받는다.
 */
const ChartGallery = lazy(async () => {
  const [mod] = await Promise.all([import('@/charts/gallery'), loadAllNamespaces()]);
  return { default: mod.ChartGallery };
});

export function ChartGalleryPage() {
  return (
    <Suspense fallback={<p className="text-sm text-muted">{t('app.loading')}</p>}>
      <ChartGallery />
    </Suspense>
  );
}
