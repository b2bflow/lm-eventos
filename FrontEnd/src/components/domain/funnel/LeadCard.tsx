import { useDraggable } from "@dnd-kit/core";
import type { KeyboardEvent, MouseEvent, PointerEvent } from "react";
import { Archive, ArchiveRestore, BadgeCheck, CalendarDays, Clock, Eye, FileText, Paperclip, Send, UserRound } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { FLAG_LABELS, OWNER_LABELS, PRODUCT_LABELS } from "@/constants/mappings";
import { formatBRL, formatDateTime, formatDay, isOverdue } from "@/lib/format";
import { openProposalPdf } from "@/hooks/useSales";
import { useLeadActions, type FunnelLead } from "@/hooks/useFunnel";

// Proposta que pode sair para o cliente (enviada também: reenviar gera o PDF de novo com nova validade)
const SENDABLE = ["rascunho", "aprovada", "enviada"];

/** Botões dentro do card não abrem o lead nem começam o arrasto. */
const stop = { onPointerDown: (e: PointerEvent) => e.stopPropagation(), onKeyDown: (e: KeyboardEvent) => e.stopPropagation() };

const CARD_CLASSES = "rounded-xl border border-border/60 bg-card p-3 space-y-2";

function ProposalAttachment({ lead }: { lead: FunnelLead }) {
  const proposal = lead.current_proposal!;
  const actions = useLeadActions(lead.id);
  const sendable = SENDABLE.includes(proposal.status);
  const again = proposal.status === "enviada";

  const send = (e: MouseEvent) => {
    e.stopPropagation();
    if (!window.confirm(`Enviar${again ? " de novo" : ""} a proposta v${proposal.version} (${formatBRL(proposal.total)}) no WhatsApp de ${lead.name || lead.phone}?`)) return;
    actions.sendProposalWhatsApp(proposal.id).catch(() => undefined);
  };

  return (
    // Versão, status e valor do PDF: o valor no alto do card é o da última proposta enviada
    <div className="rounded-lg border border-border/60 bg-secondary/30 p-1.5 space-y-1.5">
      <div className="flex items-center gap-1.5 px-0.5 text-[11px]">
        <FileText className="w-3.5 h-3.5 shrink-0 text-rose-600" />
        <span className="shrink-0 whitespace-nowrap font-medium text-foreground">Proposta v{proposal.version}</span>
        <span className="min-w-0 truncate text-muted-foreground" title={proposal.status_label}>· {proposal.status_label}</span>
        <span className="ml-auto shrink-0 font-semibold tabular-nums text-foreground">{formatBRL(proposal.total)}</span>
      </div>
      <div className="flex gap-1.5">
        <button type="button" {...stop}
          onClick={(e) => { e.stopPropagation(); openProposalPdf(proposal.id).catch(() => toast.error("Não foi possível gerar o PDF.")); }}
          title={`Abrir ${proposal.file_name}`}
          className="flex flex-1 items-center justify-center gap-1 rounded-md border border-border/70 bg-background px-2 py-1 text-[11px] font-medium text-foreground hover:border-primary/50 hover:text-primary">
          <Eye className="w-3.5 h-3.5" /> Ver PDF
        </button>
        {sendable && (
          <button type="button" {...stop} onClick={send} disabled={actions.isPending}
            title={again ? "Reenviar no WhatsApp do cliente (PDF com nova validade)" : "Enviar no WhatsApp do cliente"}
            className="flex flex-1 items-center justify-center gap-1 rounded-md bg-primary px-2 py-1 text-[11px] font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-60">
            <Send className="w-3 h-3" /> {again ? "Reenviar" : "Enviar"}
          </button>
        )}
      </div>
    </div>
  );
}

interface LeadCardContentProps {
  lead: FunnelLead;
  /** Botão rápido no rodapé: arquivar (ganho/perdido nos ativos) ou desarquivar (nos arquivados). */
  onArchive?: (lead: FunnelLead) => void;
  onUnarchive?: (lead: FunnelLead) => void;
}

/** Conteúdo do card, usado no quadro e na cópia que acompanha o mouse ao arrastar. */
export function LeadCardContent({ lead, onArchive, onUnarchive }: LeadCardContentProps) {
  const value = lead.contract_value || lead.quoted_amount;
  return (
    <>
      <div className="flex items-start justify-between gap-2">
        <h4 className="text-sm font-semibold text-foreground leading-tight line-clamp-2">{lead.name || lead.phone}</h4>
        {value ? <span className="text-sm font-bold tabular-nums text-foreground shrink-0">{formatBRL(value)}</span> : null}
      </div>

      <div className="flex flex-wrap gap-1.5 text-[11px] text-muted-foreground">
        {lead.product && (
          <span className="px-2 py-0.5 rounded-full bg-secondary text-secondary-foreground">
            {PRODUCT_LABELS[lead.product] || lead.product}
          </span>
        )}
        {lead.event_date && (
          <span className="flex items-center gap-1">
            <CalendarDays className="w-3 h-3" /> {formatDay(lead.event_date)}
          </span>
        )}
        {lead.ai_qualified_at && (
          <span className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 font-semibold"
            title="Lead qualificado pela IA">
            <BadgeCheck className="w-3 h-3" /> Qualificado IA
          </span>
        )}
        {lead.attachments?.length > 0 && (
          <span className="flex items-center gap-1">
            <Paperclip className="w-3 h-3" /> {lead.attachments.length}
          </span>
        )}
      </div>

      {lead.current_proposal && <ProposalAttachment lead={lead} />}

      {lead.flags?.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {lead.flags.map((flag) => (
            <StatusBadge key={flag} tone="warning" dot={false} className="text-[10px] px-1.5">{FLAG_LABELS[flag] || flag}</StatusBadge>
          ))}
        </div>
      )}

      <div className="flex items-center justify-between gap-2 text-[11px]">
        {lead.next_step || lead.next_action_at ? (
          <span className={cn("flex items-center gap-1 truncate", isOverdue(lead.next_action_at) ? "text-rose-600 font-semibold" : "text-muted-foreground")}>
            <Clock className="w-3 h-3 shrink-0" />
            <span className="truncate">{lead.next_step || "Próxima ação"}</span>
            {lead.next_action_at && <span className="shrink-0">{formatDateTime(lead.next_action_at)}</span>}
          </span>
        ) : (
          <span />
        )}
        <span className="flex items-center gap-2 shrink-0">
          {onArchive && (
            <button type="button" {...stop} onClick={(e) => { e.stopPropagation(); onArchive(lead); }}
              title="Arquivar o card (vai para a aba Arquivados)"
              className="flex items-center gap-1 rounded-md px-1.5 py-0.5 text-muted-foreground hover:bg-secondary hover:text-foreground">
              <Archive className="w-3 h-3" /> Arquivar
            </button>
          )}
          {onUnarchive && (
            <button type="button" {...stop} onClick={(e) => { e.stopPropagation(); onUnarchive(lead); }}
              title="Devolver o card para os ativos"
              className="flex items-center gap-1 rounded-md px-1.5 py-0.5 text-muted-foreground hover:bg-secondary hover:text-foreground">
              <ArchiveRestore className="w-3 h-3" /> Desarquivar
            </button>
          )}
          <span className="flex items-center gap-1 text-muted-foreground">
            <UserRound className="w-3 h-3" /> {OWNER_LABELS[lead.owner || "sdr"]}
          </span>
        </span>
      </div>
    </>
  );
}

interface LeadCardProps extends LeadCardContentProps {
  onOpen: (id: string) => void;
}

export function LeadCard({ lead, onOpen, ...quick }: LeadCardProps) {
  // Ao arrastar, quem anda é a cópia do DragOverlay (por cima de tudo); o card fica no lugar, apagado.
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: lead.id,
    data: { stage: lead.customer_state_now, lead },
  });

  return (
    <div
      ref={setNodeRef}
      {...listeners}
      {...attributes}
      onClick={() => onOpen(lead.id)}
      className={cn(
        CARD_CLASSES, "cursor-grab active:cursor-grabbing touch-none select-none hover:border-primary/50 transition-colors",
        isDragging && "opacity-40 border-dashed border-primary/50"
      )}
    >
      <LeadCardContent lead={lead} {...quick} />
    </div>
  );
}

/** Cópia do card que segue o mouse durante o arrasto (renderizada no DragOverlay).
 *  `hint`: o que acontece ao soltar ali (ex.: sobre a aba Arquivados, que fica escondida atrás do card). */
export function LeadCardOverlay({ lead, hint }: { lead: FunnelLead; hint?: string | null }) {
  return (
    <div className={cn(CARD_CLASSES, "cursor-grabbing shadow-2xl ring-2 ring-primary/40 rotate-[1.5deg]", hint && "ring-primary")}>
      {hint && (
        <div className="-mx-3 -mt-3 mb-2 flex items-center gap-1.5 rounded-t-xl bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground">
          <Archive className="w-3.5 h-3.5" /> {hint}
        </div>
      )}
      <LeadCardContent lead={lead} />
    </div>
  );
}
