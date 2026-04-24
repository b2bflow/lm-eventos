import { useDateFilter } from '@/contexts/DateFilterContext';
import { useDashboardMetrics } from '@/hooks/useMetrics';
import { format } from 'date-fns';
import { GenericAreaChart } from '../../shared/charts/GenericAreaChart';

export function ConversionRateChart() {
  const { dateRange } = useDateFilter();
  const start = dateRange?.from ? format(dateRange.from, 'yyyy-MM-dd') : undefined;
  const end = dateRange?.to ? format(dateRange.to, 'yyyy-MM-dd') : undefined;

  const { data: metrics, isLoading } = useDashboardMetrics(start, end);

  return (
    <GenericAreaChart 
      title="Novos Pacientes"
      subtitle={
        <>
          {metrics?.new_leads_count ?? 0} novos nos atendimentos do período
        </>
      }
      value={`${metrics?.new_leads_rate ?? 0}%`}
      data={metrics ? { labels: metrics.labels, values: metrics.new_leads_series } : undefined}
      isLoading={isLoading}
      colorHex="#10b981" // Verde
      gradientId="colorNewLead"
    />
  );
}