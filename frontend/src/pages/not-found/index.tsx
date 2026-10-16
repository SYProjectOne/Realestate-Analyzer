import { Link, useSearchParams } from 'react-router';
import { Card } from '@/components/Card';
import { t } from '@/i18n';
import { PageShell } from '@/layout/PageShell';

/** 지역·기준일·상황 쿼리만 남긴 search(진입 청크에 화면 공용 조각을 끌어오지 않으려고 여기 둔다) */
function useKeepSearch(): string {
  const [params] = useSearchParams();
  const keep = new URLSearchParams();
  for (const key of ['region', 'snapshot', 'scenario']) {
    const v = params.get(key);
    if (v) keep.set(key, v);
  }
  const s = keep.toString();
  return s ? `?${s}` : '';
}

/** 없는 주소(목업 §9): "찾는 화면이 없어요" + 홈으로(지역·기준일·상황 쿼리 유지, N12). 휴대폰에서도 읽기 전용으로 연다 */
export function NotFoundPage() {
  const search = useKeepSearch();
  return (
    <PageShell title={t('page.notFound.title')}>
      <Card padding="lg" className="flex flex-col items-start gap-2">
        <Link
          to={{ pathname: '/', search }}
          className="text-sm font-medium text-accent underline"
          data-testid="not-found-home"
        >
          {t('page.notFound.home')}
        </Link>
      </Card>
    </PageShell>
  );
}
