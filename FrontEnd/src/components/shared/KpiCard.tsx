import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { TONE_CLASSES, type Tone } from "@/lib/tones";

interface KpiCardProps {
  label: string;
  value: ReactNode;
  caption?: ReactNode;
  icon?: LucideIcon;
  tone?: Tone;
  // Mostra "..." no lugar do valor enquanto a query carrega.
  loading?: boolean;
  onClick?: () => void;
  className?: string;
}

// Card de indicador do dashboard (agendamentos, comparecimento, vendas...), no visual dos cards do core.
export function KpiCard({ label, value, caption, icon: Icon, tone = "primary", loading, onClick, className }: KpiCardProps) {
  return (
    <div
      onClick={onClick}
      className={cn(
        "glass rounded-2xl p-4 sm:p-6 h-full min-w-0 relative overflow-hidden flex flex-col justify-between border border-border/50 transition-all duration-300",
        onClick && "cursor-pointer card-hover hover:border-primary/50",
        className,
      )}
    >
      <div className="flex items-start justify-between gap-2 sm:gap-3">
        <h3 className="min-w-0 text-xs font-semibold uppercase tracking-wide sm:tracking-wider text-muted-foreground [overflow-wrap:anywhere]">{label}</h3>
        {Icon && (
          <span className={cn("w-8 h-8 sm:w-10 sm:h-10 rounded-lg sm:rounded-xl flex items-center justify-center border shrink-0", TONE_CLASSES[tone])}>
            <Icon className="w-4 h-4 sm:w-5 sm:h-5" />
          </span>
        )}
      </div>
      <div className="mt-4 space-y-1">
        <p className="text-2xl sm:text-3xl font-bold tracking-tight text-foreground tabular-nums [overflow-wrap:anywhere]">{loading ? "..." : value}</p>
        {caption && <div className="text-xs text-muted-foreground">{caption}</div>}
      </div>
    </div>
  );
}
