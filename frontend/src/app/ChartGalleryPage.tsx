import { lazy, Suspense, type ComponentType } from 'react';
import { t } from '@/i18n';
import { PageShell } from '@/layout/PageShell';

/**
 * `/__charts` (dev 전용) — WP6b의 `src/charts/gallery/ChartGallery.tsx`를 등록한다.
 * 파일이 아직 없으면(glob 결과 비어 있음) 안내만 보인다. 빌드는 깨지지 않는다.
 */
const modules = import.meta.glob<{ ChartGallery?: ComponentType; default?: ComponentType }>(
  '../charts/gallery/ChartGallery.tsx',
);
const loader = Object.values(modules)[0];

const Gallery = loader
  ? lazy(async () => {
      const mod = await loader();
      const Component = mod.ChartGallery ?? mod.default;
      return { default: Component ?? Missing };
    })
  : null;

function Missing() {
  return <p className="text-sm text-muted">{t('app.chartGalleryMissing')}</p>;
}

export function ChartGalleryPage() {
  return (
    <PageShell title={t('app.chartGallery')}>
      {Gallery ? (
        <Suspense fallback={<p className="text-sm text-muted">{t('app.loading')}</p>}>
          <Gallery />
        </Suspense>
      ) : (
        <Missing />
      )}
    </PageShell>
  );
}
