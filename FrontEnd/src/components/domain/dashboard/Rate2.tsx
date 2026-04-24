import { useDateFilter } from '@/contexts/DateFilterContext';
import { useDashboardMetrics } from '@/hooks/useMetrics';
import { format } from 'date-fns';
import { GenericAreaChart } from '../../shared/charts/GenericAreaChart';

export function CancelRateChart2() {
  const { dateRange } = useDateFilter();
  const start = dateRange?.from ? format(dateRange.from, 'yyyy-MM-dd') : undefined;
  const end = dateRange?.to ? format(dateRange.to, 'yyyy-MM-dd') : undefined;

  const { data: metrics, isLoading } = useDashboardMetrics(start, end);

  return (
    <GenericAreaChart 
      title="Incorrências"
      subtitle={
        <>
          {metrics?.inacurrences_count ?? 0} incorrências nos atendimentos do período
        </>
      }
      value={`${metrics?.inacurrences_rate ?? 0}%`}
      data={metrics ? { labels: metrics.labels, values: metrics.inacurrences_series } : undefined}
      isLoading={isLoading}
      colorHex="#ef4444" 
      gradientId="colorInacurrence"
    />
  );
}