import { lazy, Suspense } from 'react';
import { Skeleton } from './ui';
import type { PriceChartProps } from './PriceChartImpl';

const Impl = lazy(() => import('./PriceChartImpl'));

export default function PriceChart(props: PriceChartProps) {
  return (
    <Suspense fallback={<Skeleton className="h-72 w-full sm:h-80" />}>
      <Impl {...props} />
    </Suspense>
  );
}
