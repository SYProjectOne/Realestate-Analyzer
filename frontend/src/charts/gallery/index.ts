/**
 * 차트 갤러리(개발 전용). 라우트 `/__charts`는 WP6a가 dev에서만 lazy로 등록한다:
 *   const ChartGallery = lazy(() => import('@/charts/gallery').then((m) => ({ default: m.ChartGallery })));
 * 계약 예시 JSON을 묶으므로 `@/charts`(index.ts)에서는 다시 내보내지 않는다(본 번들 크기 보호).
 */
export { ChartGallery, GALLERY_CASES, type GalleryCase, type GalleryState } from './ChartGallery';
