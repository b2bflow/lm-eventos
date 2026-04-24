import { useDashboardMetrics } from "@/hooks/useMetrics";
import { useDateFilter } from "@/contexts/DateFilterContext";
import { format } from "date-fns";
import { GenericStatCard } from "@/components/shared/cards/GenericStatCard";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { CalendarClock, CalendarRange, CircleDollarSign, HandCoins, PartyPopper, PhoneOff, Target, Users } from "lucide-react";

interface DashboardGridProps {
  role: "admin" | "user";
}

export function DashboardGrid({ role }: DashboardGridProps) {
  const { dateRange } = useDateFilter();
  const start = dateRange?.from ? format(dateRange.from, 'yyyy-MM-dd') : undefined;
  const end = dateRange?.to ? format(dateRange.to, 'yyyy-MM-dd') : undefined;

  const { data: metrics, isLoading } = useDashboardMetrics(start, end);
  const currency = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
  const trendData = (metrics?.labels || []).map((label, index) => ({
    label,
    pipeline: metrics?.lead_pipeline_series?.[index] || 0,
    confirmed: metrics?.confirmed_events_series?.[index] || 0,
    projectedRevenue: metrics?.projected_revenue_series?.[index] || 0,
  }));

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-6 gap-5">
        <GenericStatCard
          title="Total Geral de Leads"
          value={isLoading ? "..." : metrics?.total_leads_general || 0}
          subtext={`${metrics?.total_leads || 0} dentro do período filtrado`}
          icon={Users}
          variant="default"
        />
        {/* <GenericStatCard
          title="Receita Projetada"
          value={isLoading ? "..." : currency.format(metrics?.projected_revenue || 0)}
          subtext="Soma dos leads ativos no funil"
          icon={CircleDollarSign}
          variant="primary"
        />
        <GenericStatCard
          title="Receita Confirmada"
          value={isLoading ? "..." : currency.format(metrics?.confirmed_revenue || 0)}
          subtext={`${metrics?.events_confirmed || 0} eventos fechados no período`}
          icon={HandCoins}
          variant="accent"
        /> */}
        <GenericStatCard
          title="Conversão por Venda"
          value={isLoading ? "..." : `${metrics?.sales_conversion_rate || 0}%`}
          subtext={`${metrics?.events_confirmed || 0} leads viraram tag Venda`}
          icon={Target}
          variant="accent"
        />
        <GenericStatCard
          title="Taxa de Interrupção"
          value={isLoading ? "..." : `${metrics?.interruption_rate || 0}%`}
          subtext={`${metrics?.interruption_count || 0} iniciaram e não chegaram em Negociando`}
          icon={PhoneOff}
          variant="destructive"
        />
        <GenericStatCard
          title="Ocupação de Agenda"
          value={isLoading ? "..." : `${metrics?.schedule_occupancy_rate || 0}%`}
          subtext={`${metrics?.upcoming_events_count || 0} datas ocupadas nos próximos 30 dias`}
          icon={CalendarClock}
          variant="default"
        />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[1.3fr_0.7fr] gap-5">
        <div className="glass rounded-2xl p-6 border border-border/50">
          <div className="flex items-start justify-between mb-5">
            <div>
              <h3 className="text-lg font-semibold">Funil e Receita Diária</h3>
              <p className="text-sm text-muted-foreground">Evolução de entrada de leads, fechamentos e potencial financeiro.</p>
            </div>
            <PartyPopper className="w-5 h-5 text-primary" />
          </div>

          <div className="h-[320px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={trendData}>
                <defs>
                  <linearGradient id="projectedRevenue" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#0ea5e9" stopOpacity={0.35} />
                    <stop offset="95%" stopColor="#0ea5e9" stopOpacity={0.04} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
                <XAxis dataKey="label" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis
                  yAxisId="left"
                  tick={{ fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  allowDecimals={false}
                />
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  tick={{ fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={(value) => `R$${Math.round(Number(value) / 1000)}k`}
                />
                <Tooltip
                  formatter={(value: number, name: string) => {
                    if (name === "projectedRevenue") return [currency.format(value), "Receita Projetada"];
                    if (name === "confirmed") return [value, "Eventos Confirmados"];
                    return [value, "Leads no Pipeline"];
                  }}
                  contentStyle={{ borderRadius: 16, border: "1px solid hsl(var(--border))", backgroundColor: "hsl(var(--card))" }}
                />
                <Bar yAxisId="left" dataKey="pipeline" name="pipeline" fill="#f59e0b" radius={[6, 6, 0, 0]} />
                <Bar yAxisId="left" dataKey="confirmed" name="confirmed" fill="#10b981" radius={[6, 6, 0, 0]} />
                <Area yAxisId="right" type="monotone" dataKey="projectedRevenue" name="projectedRevenue" stroke="#0ea5e9" fill="url(#projectedRevenue)" strokeWidth={2.5} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="glass rounded-2xl p-6 border border-border/50">
          <div className="flex items-start justify-between mb-5">
            <div>
              <h3 className="text-lg font-semibold">Saúde do Pipeline</h3>
              <p className="text-sm text-muted-foreground">Onde o operador deve atacar gargalos agora.</p>
            </div>
            <Users className="w-5 h-5 text-primary" />
          </div>

          <div className="space-y-4">
            <div className="rounded-xl bg-secondary/40 p-4">
              <div className="text-xs uppercase tracking-wider text-muted-foreground">Em análise</div>
              <div className="mt-2 text-3xl font-bold">{metrics?.analysis_count || 0}</div>
            </div>
            <div className="rounded-xl bg-amber-500/10 p-4 border border-amber-500/20">
              <div className="text-xs uppercase tracking-wider text-amber-700">Aguardando orçamento</div>
              <div className="mt-2 text-3xl font-bold text-amber-700">{metrics?.budget_count || 0}</div>
            </div>
            <div className="rounded-xl bg-sky-500/10 p-4 border border-sky-500/20">
              <div className="text-xs uppercase tracking-wider text-sky-700">Negociando</div>
              <div className="mt-2 text-3xl font-bold text-sky-700">{metrics?.negotiating_count || 0}</div>
            </div>
            <div className="rounded-xl bg-rose-500/10 p-4 border border-rose-500/20">
              <div className="text-xs uppercase tracking-wider text-rose-700">Perdidos</div>
              <div className="mt-2 text-3xl font-bold text-rose-700">{metrics?.lost_count || 0}</div>
            </div>
            <div className="rounded-xl border border-border/60 p-4">
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">Ticket médio fechado</span>
                <CalendarRange className="w-4 h-4 text-muted-foreground" />
              </div>
              <div className="mt-2 text-2xl font-semibold">{currency.format(metrics?.average_ticket || 0)}</div>
            </div>
          </div>
        </div>
      </div>

      <div className="glass rounded-2xl p-6 border border-border/50">
        <div className="flex items-start justify-between mb-5">
          <div>
            <h3 className="text-lg font-semibold">Cadência de Fechamentos</h3>
            <p className="text-sm text-muted-foreground">Visão direta dos eventos confirmados ao longo do período filtrado.</p>
          </div>
          <Target className="w-5 h-5 text-primary" />
        </div>

        <div className="h-[240px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={trendData}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
              <XAxis dataKey="label" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis allowDecimals={false} tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
              <Tooltip
                formatter={(value: number) => [value, "Eventos confirmados"]}
                contentStyle={{ borderRadius: 16, border: "1px solid hsl(var(--border))", backgroundColor: "hsl(var(--card))" }}
              />
              <Bar dataKey="confirmed" fill="#10b981" radius={[8, 8, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
