import { useQuery } from "@tanstack/react-query";
import api from "@/services/api";

export interface DashboardMetrics {
  labels: string[];
  lead_pipeline_series: number[];
  confirmed_events_series: number[];
  projected_revenue_series: number[];
  total_leads_general: number;
  total_leads: number;
  analysis_count: number;
  budget_count: number;
  negotiating_count: number;
  events_confirmed: number;
  lost_count: number;
  interruption_count: number;
  projected_revenue: number;
  confirmed_revenue: number;
  conversion_rate: number;
  sales_conversion_rate: number;
  interruption_rate: number;
  schedule_occupancy_rate: number;
  upcoming_events_count: number;
  average_ticket: number;
}

export const useDashboardMetrics = (startDate?: string, endDate?: string) => {
  return useQuery({
    queryKey: ['dashboard-metrics', startDate, endDate],
    queryFn: async () => {
      const { data } = await api.get('/analytics/dashboard/metrics/', {
        params: { start_date: startDate, end_date: endDate }
      });
      return data as DashboardMetrics;
    },
  });
};
