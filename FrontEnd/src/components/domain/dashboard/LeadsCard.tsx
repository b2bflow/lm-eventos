import { Users, TrendingUp } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useDashboardMetrics } from "@/hooks/useMetrics"; 
import { useDateFilter } from "@/contexts/DateFilterContext";
import { format } from "date-fns";

export function LeadsCard() {
  const navigate = useNavigate();
  const { dateRange } = useDateFilter();

  const start = dateRange?.from ? format(dateRange.from, 'yyyy-MM-dd') : undefined;
  const end = dateRange?.to ? format(dateRange.to, 'yyyy-MM-dd') : undefined;

  const { data: metrics, isLoading } = useDashboardMetrics(start, end);

  return (
    <div 
      onClick={() => navigate("/leads")}
      className="glass rounded-2xl p-6 card-hover h-full relative overflow-hidden group cursor-pointer flex flex-col justify-between"
    >
      <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-br from-primary/10 to-transparent rounded-bl-full" />
      <div className="absolute bottom-0 left-0 w-24 h-24 bg-gradient-to-tr from-primary/5 to-transparent rounded-tr-full" />
      
      <div className="flex items-start justify-between relative z-10">
        <div className="space-y-4">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Pacientes Cadastrados</h3>
          <div className="w-12 h-12 rounded-xl bg-primary/10 flex items-center justify-center border border-primary/20">
            <Users className="w-6 h-6 text-primary" />
          </div>
        </div>

        <div className="text-right space-y-1">
          <div className="flex justify-end">
            <TrendingUp className="w-4 h-4 text-green-500/50" />
          </div>
          
          <div className="flex flex-col items-end gap-1 mt-3">
            <span className="text-4xl font-bold tracking-tight text-foreground">
              {isLoading ? "..." : (metrics?.total_system_customers ?? 0)}
            </span>
            <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">
              de {isLoading ? "..." : (metrics?.total_system_conversations ?? 0)} conversas
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}