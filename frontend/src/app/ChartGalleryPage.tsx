import { lazy, Suspense } from 'react';
import { t } from '@/i18n';

/**
 * `/__charts` (dev 전용, routes.tsx가 DEV·MSW 모드에서만 등록) — WP6b의 `@/charts/gallery`.
 * 예시 JSON 번들이라 지연 로드한다. 제목(h1)은 갤러리가 갖는다.
 */
const ChartGallery = lazy(async () => ({
  default: (await import('@/charts/gallery')).ChartGallery,
}));

export function ChartGalleryPage() {
  return (
    <Suspense fallback={<p className="text-sm text-muted">{t('app.loading')}</p>}>
      <ChartGallery />
    </Suspense>
  );
}
