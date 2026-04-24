import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { useMemo } from 'react';

interface GenericAreaChartProps {
  title: string;
  subtitle: React.ReactNode;
  value: string | number;
  data: { labels: string[]; values: number[] } | undefined;
  isLoading: boolean;
  colorHex: string; 
  gradientId: string;
}

export function GenericAreaChart({
  title,
  subtitle,
  value,
  data,
  isLoading,
  colorHex,
  gradientId
}: GenericAreaChartProps) {
  
  const chartData = useMemo(() => {
    if (!data || !Array.isArray(data.labels)) return [];
    
    return data.labels.map((label, i) => ({
      name: label,
      value: data.values && data.values[i] !== undefined ? data.values[i] : 0
    }));
  }, [data]);

  return (
    <div className="glass rounded-2xl p-6 h-full relative overflow-hidden border border-white/10 flex flex-col justify-between">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-sm font-semibold">{title}</h3>
          <div className="text-xs text-muted-foreground mt-1">
            {subtitle}
          </div>
        </div>
        <span className="text-3xl font-bold text-foreground">
          {isLoading ? '...' : value}
        </span>
      </div>

      <div className="h-44 w-full">
        <ResponsiveContainer width="100%" height="100%">
          {/* CORREÇÃO 1: Margem left voltou para 0 para não empurrar para fora da tela */}
          <AreaChart data={chartData} margin={{ top: 5, bottom: 5, left: 0, right: 0 }}>
            <defs>
              <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={colorHex} stopOpacity={0.3} />
                <stop offset="95%" stopColor={colorHex} stopOpacity={0} />
              </linearGradient>
            </defs>
            <XAxis
              dataKey="name"
              tick={{ fontSize: 10 }}
              axisLine={false}
              tickLine={false}
              minTickGap={20}
            />
            <YAxis
              domain={[0, 100]} 
              ticks={[0, 25, 50, 75, 100]} 
              tick={{ fontSize: 10 }}
              tickFormatter={(v) => `${v}%`} 
              width={45} 
              axisLine={false}
              tickLine={false}
            />
            <Tooltip 
              contentStyle={{ borderRadius: '8px', border: 'none', backgroundColor: 'hsl(var(--card))' }}
              itemStyle={{ color: colorHex, fontWeight: 'bold' }}
              formatter={(value: number) => [`${value}%`, title]}
            />
            <Area
              type="monotone" 
              dataKey="value"
              stroke={colorHex}
              fillOpacity={1}
              fill={`url(#${gradientId})`}
              strokeWidth={2}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}