import { useEffect, useState } from "react";
import { useDroppable } from "@dnd-kit/core";
import { Loader2, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { LEAD_STAGE_TONES, LEAD_STATUS_LABELS, type LeadStage } from "@/constants/mappings";
import { TONE_DOT_CLASSES } from "@/lib/tones";
import { formatBRL } from "@/lib/format";
import { fetchMoreForStage, type FunnelBoard, type FunnelFilters, type FunnelLead } from "@/hooks/useFunnel";
import { LeadCard } from "./LeadCard";

interface ColumnProps {
  stage: LeadStage;
  label: string;
  leads: FunnelLead[];
  count: number;
  hasMore: boolean;
  loadingMore: boolean;
  onLoadMore: () => void;
  onOpen: (id: string) => void;
  /** Só na coluna "Lead qualificado", onde entram os cards criados à mão. */
  onAdd?: () => void;
  onArchive?: (lead: FunnelLead) => void;
  onUnarchive?: (lead: FunnelLead) => void;
}

function Column({ stage, label, leads, count, hasMore, loadingMore, onLoadMore, onOpen, onAdd, onArchive, onUnarchive }: ColumnProps) {
  const { setNodeRef, isOver } = useDroppable({ id: stage });
  const value = leads.reduce((sum, l) => sum + (l.contract_value || l.quoted_amount || 0), 0);
  return (
    <div
      ref={setNodeRef}
      aria-label={label}
      className={cn(
        // A coluna estica até o fim da tela (altura do quadro), com ou sem cards
        "w-[80vw] max-w-72 sm:w-72 shrink-0 flex flex-col min-h-0 rounded-2xl border border-border/50 bg-muted/30 transition-colors",
        isOver && "border-primary/60 bg-primary/5"
      )}
    >
      <header className="px-3 pt-3 pb-2 border-b border-border/40">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-foreground">
          <span className={cn("w-2 h-2 rounded-full", TONE_DOT_CLASSES[LEAD_STAGE_TONES[stage] ?? "neutral"])} aria-hidden />
          <span className="truncate">{label}</span>
          <span className="ml-auto text-xs font-normal text-muted-foreground tabular-nums">{count}</span>
        </h3>
        <div className="mt-1 text-xs text-muted-foreground">{value > 0 ? `${formatBRL(value)}${hasMore ? " nesta página" : ""}` : "—"}</div>
      </header>
      <div className="flex-1 min-h-0 overflow-y-auto p-2 space-y-2">
        {onAdd && (
          <button type="button" onClick={onAdd}
            className="w-full flex items-center justify-center gap-1.5 rounded-xl border border-dashed border-border py-2 text-xs font-medium text-muted-foreground hover:border-primary/60 hover:text-primary hover:bg-primary/5 transition-colors">
            <Plus className="w-3.5 h-3.5" /> Novo card
          </button>
        )}
        {leads.length === 0 && <p className="px-1 py-4 text-center text-xs text-muted-foreground">Nenhum lead nesta etapa.</p>}
        {leads.map((lead) => (
          <LeadCard key={lead.id} lead={lead} onOpen={onOpen} onArchive={onArchive} onUnarchive={onUnarchive} />
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
  /** Colunas na ordem (ativos: todas as etapas; arquivados: ganho e perdido). */
  stages: readonly LeadStage[];
  /** Nome da coluna quando difere da etapa (ex.: "Ganho" para contrato assinado nos arquivados). */
  labels?: Partial<Record<LeadStage, string>>;
  filters: FunnelFilters;
  onOpen: (id: string) => void;
  onAdd?: () => void;
  /** Botão "Arquivar" nos cards destas etapas. */
  archivableStages?: readonly LeadStage[];
  onArchive?: (lead: FunnelLead) => void;
  onUnarchive?: (lead: FunnelLead) => void;
}

/** Colunas do quadro. O arrasto (DndContext) fica na página, para soltar o card também nas abas do cabeçalho. */
export function FunnelBoardView({ board, stages, labels, filters, onOpen, onAdd, archivableStages = [], onArchive, onUnarchive }: FunnelBoardViewProps) {
  // Páginas extras carregadas por coluna ("Carregar mais"), zeradas quando o quadro recarrega.
  const [extra, setExtra] = useState<Partial<Record<LeadStage, { leads: FunnelLead[]; hasMore: boolean }>>>({});
  const [loadingStage, setLoadingStage] = useState<LeadStage | null>(null);
  useEffect(() => setExtra({}), [board]);

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
    // Ocupa o resto da tela: base 0px (não 0%) faz a altura vir do espaço livre, não da quantidade de cards
    <div className="grow basis-0 min-h-[24rem] flex gap-4 overflow-x-auto pb-2">
      {stages.map((stage) => {
        const column = board[stage];
        if (!column) return null;
        const leads = [...column.results, ...(extra[stage]?.leads ?? [])];
        return (
          <Column
            key={stage}
            stage={stage}
            label={labels?.[stage] ?? LEAD_STATUS_LABELS[stage]}
            leads={leads}
            count={column.count}
            hasMore={extra[stage] ? extra[stage]!.hasMore : column.has_more}
            loadingMore={loadingStage === stage}
            onLoadMore={() => loadMore(stage)}
            onOpen={onOpen}
            onAdd={stage === "QUALIFIED" ? onAdd : undefined}
            onArchive={archivableStages.includes(stage) ? onArchive : undefined}
            onUnarchive={onUnarchive}
          />
        );
      })}
    </div>
  );
}
