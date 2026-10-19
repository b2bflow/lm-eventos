import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

// Barra de filtros das telas de listagem: campos à esquerda e legenda ou ações à direita.
export function FilterBar({ children, right, className }: { children: ReactNode; right?: ReactNode; className?: string }) {
  return (
    <div className={cn("glass rounded-2xl border border-border/50 flex flex-col gap-3 p-3 lg:flex-row lg:items-center lg:justify-between", className)}>
      <div className="flex flex-wrap items-center gap-2">{children}</div>
      {right && <div className="flex flex-wrap items-center gap-3 lg:justify-end">{right}</div>}
    </div>
  );
}

export interface LegendItem {
  label: string;
  // Classe de cor do ponto (ex.: "bg-emerald-500").
  colorClass: string;
}

// Legenda com pontos coloridos, para explicar as cores de uma agenda ou de um quadro.
export function Legend({ items, className }: { items: LegendItem[]; className?: string }) {
  return (
    <div className={cn("flex flex-wrap items-center gap-3 text-xs text-muted-foreground", className)}>
      {items.map((item) => (
        <span key={item.label} className="inline-flex items-center gap-1.5">
          <span className={cn("w-2 h-2 rounded-full", item.colorClass)} aria-hidden />
          {item.label}
        </span>
      ))}
    </div>
  );
}
