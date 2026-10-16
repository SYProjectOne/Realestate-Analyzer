import type { ReactNode } from 'react';
import { Card, SectionHeader } from '@/components';

/**
 * G3 머리 구역 카드(목업 Detail .card): 질문형 제목 h2 = 구역 이름(`aria-labelledby`). data-tier 로 순서를 테스트한다.
 */
export function Tier({
  tier,
  title,
  hint,
  actions,
  children,
  className = '',
}: {
  tier: string;
  title: string;
  hint?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  const id = `g3-tier-${tier}`;
  return (
    <Card
      as="section"
      aria-labelledby={id}
      data-tier={tier}
      padding="lg"
      className={`flex min-w-0 flex-col gap-4 ${className}`}
    >
      <SectionHeader id={id} title={title} hint={hint} actions={actions} />
      {children}
    </Card>
  );
}
