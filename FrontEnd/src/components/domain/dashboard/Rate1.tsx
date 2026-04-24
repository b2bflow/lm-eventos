import { useDateFilter } from '@/contexts/DateFilterContext';
import { useDashboardMetrics } from '@/hooks/useMetrics';
import { format } from 'date-fns';
import { GenericAreaChart } from '../../shared/charts/GenericAreaChart';

export function CancelRateChart1() {
  const { dateRange } = useDateFilter();
  const start = dateRange?.from ? format(dateRange.from, 'yyyy-MM-dd') : undefined;
  const end = dateRange?.to ? format(dateRange.to, 'yyyy-MM-dd') : undefined;

  const { data: metrics, isLoading } = useDashboardMetrics(start, end);

  return (
    <GenericAreaChart 
      title="Retornos"
      subtitle={
        <>
          {metrics?.returns_count ?? 0} retornos nos atendimentos do período
        </>
      }
      value={`${metrics?.returns_rate ?? 0}%`}
      data={metrics ? { labels: metrics.labels, values: metrics.returns_series } : undefined}
      isLoading={isLoading}
      colorHex="#f97316"
      gradientId="colorReturn"
    />
  );
}