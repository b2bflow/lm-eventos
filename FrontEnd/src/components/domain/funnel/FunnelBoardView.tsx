import { useEffect, useState } from "react";
import { DndContext, PointerSensor, TouchSensor, useDroppable, useSensor, useSensors, type DragEndEvent } from "@dnd-kit/core";
import { Loader2, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { LEAD_STAGE_TONES, LEAD_STATUS_LABELS, LEAD_STATUS_OPTIONS, type LeadStage } from "@/constants/mappings";
import { TONE_DOT_CLASSES } from "@/lib/tones";
import { formatBRL } from "@/lib/format";
import { fetchMoreForStage, type FunnelBoard, type FunnelFilters, type FunnelLead } from "@/hooks/useFunnel";
import { LeadCard } from "./LeadCard";

interface ColumnProps {
  stage: LeadStage;
  leads: FunnelLead[];
  count: number;
  hasMore: boolean;
  loadingMore: boolean;
  onLoadMore: () => void;
  onOpen: (id: string) => void;
  /** Só na coluna "Novo lead", onde entram os cards criados à mão. */
  onAdd?: () => void;
}

function Column({ stage, leads, count, hasMore, loadingMore, onLoadMore, onOpen, onAdd }: ColumnProps) {
  const { setNodeRef, isOver } = useDroppable({ id: stage });
  const value = leads.reduce((sum, l) => sum + (l.contract_value || l.quoted_amount || 0), 0);
  return (
    <div
      ref={setNodeRef}
      aria-label={LEAD_STATUS_LABELS[stage]}
      className={cn(
        "w-[80vw] max-w-72 sm:w-72 shrink-0 flex flex-col rounded-2xl border border-border/50 bg-muted/30 max-h-[calc(100vh-15rem)] transition-colors",
        isOver && "border-primary/60 bg-primary/5"
      )}
    >
      <header className="px-3 pt-3 pb-2 border-b border-border/40">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-foreground">
          <span className={cn("w-2 h-2 rounded-full", TONE_DOT_CLASSES[LEAD_STAGE_TONES[stage] ?? "neutral"])} aria-hidden />
          <span className="truncate">{LEAD_STATUS_LABELS[stage]}</span>
          <span className="ml-auto text-xs font-normal text-muted-foreground tabular-nums">{count}</span>
        </h3>
        <div className="mt-1 text-xs text-muted-foreground">{value > 0 ? `${formatBRL(value)}${hasMore ? " nesta página" : ""}` : "—"}</div>
      </header>
      <div className="flex-1 overflow-y-auto p-2 space-y-2 min-h-24">
        {onAdd && (
          <button type="button" onClick={onAdd}
            className="w-full flex items-center justify-center gap-1.5 rounded-xl border border-dashed border-border py-2 text-xs font-medium text-muted-foreground hover:border-primary/60 hover:text-primary hover:bg-primary/5 transition-colors">
            <Plus className="w-3.5 h-3.5" /> Novo card
          </button>
        )}
        {leads.length === 0 && <p className="px-1 py-4 text-center text-xs text-muted-foreground">Nenhum lead nesta etapa.</p>}
        {leads.map((lead) => (
          <LeadCard key={lead.id} lead={lead} onOpen={onOpen} />
        ))}
        {hasMore && (
          <Button variant="ghost" size="sm" className="w-full text-xs" onClick={onLoadMore} disabled={loadingMore}>
            {loadingMore ? <Loader2 className="w-4 h-4 animate-spin" /> : `Carregar mais (${count - leads.length})`}
          </Button>
        )}
      </div>
    </div>
  );
}

interface FunnelBoardViewProps {
  board: FunnelBoard;
  filters: FunnelFilters;
  onOpen: (id: string) => void;
  onMove: (leadId: string, from: LeadStage, to: LeadStage) => void;
  onAdd?: () => void;
}

export function FunnelBoardView({ board, filters, onOpen, onMove, onAdd }: FunnelBoardViewProps) {
  // Páginas extras carregadas por coluna ("Carregar mais"), zeradas quando o quadro recarrega.
  const [extra, setExtra] = useState<Partial<Record<LeadStage, { leads: FunnelLead[]; hasMore: boolean }>>>({});
  const [loadingStage, setLoadingStage] = useState<LeadStage | null>(null);
  useEffect(() => setExtra({}), [board]);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 250, tolerance: 8 } })
  );

  const handleDragEnd = (event: DragEndEvent) => {
    const to = event.over?.id as LeadStage | undefined;
    const from = event.active.data.current?.stage as LeadStage | undefined;
    if (!to || !from || to === from) return;
    onMove(String(event.active.id), from, to);
  };

  const loadMore = async (stage: LeadStage) => {
    const current = [...board[stage].results, ...(extra[stage]?.leads ?? [])];
    setLoadingStage(stage);
    try {
      const column = await fetchMoreForStage(stage, current.length, filters);
      const ids = new Set(current.map((l) => l.id));
      setExtra((prev) => ({
        ...prev,
        [stage]: { leads: [...(prev[stage]?.leads ?? []), ...column.results.filter((l) => !ids.has(l.id))], hasMore: column.has_more },
      }));
    } finally {
      setLoadingStage(null);
    }
  };

  return (
    <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
      <div className="flex gap-4 overflow-x-auto pb-2 items-start">
        {LEAD_STATUS_OPTIONS.map((stage) => {
          const column = board[stage];
          const leads = [...column.results, ...(extra[stage]?.leads ?? [])];
          return (
            <Column
              key={stage}
              stage={stage}
              leads={leads}
              count={column.count}
              hasMore={extra[stage] ? extra[stage]!.hasMore : column.has_more}
              loadingMore={loadingStage === stage}
              onLoadMore={() => loadMore(stage)}
              onOpen={onOpen}
              onAdd={stage === "NEW_LEAD" ? onAdd : undefined}
            />
          );
        })}
      </div>
    </DndContext>
  );
}
