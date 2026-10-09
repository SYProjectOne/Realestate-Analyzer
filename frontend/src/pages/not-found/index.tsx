import { t } from '@/i18n';
import { PageShell } from '@/layout/PageShell';

export function NotFoundPage() {
  return <PageShell title={t('page.notFound.title')} />;
}
