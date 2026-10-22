import { useDraggable } from "@dnd-kit/core";
import { BadgeCheck, CalendarDays, Clock, Paperclip, UserRound } from "lucide-react";
import { cn } from "@/lib/utils";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { FLAG_LABELS, OWNER_LABELS, PRODUCT_LABELS } from "@/constants/mappings";
import { formatBRL, formatDateTime, formatDay, isOverdue } from "@/lib/format";
import type { FunnelLead } from "@/hooks/useFunnel";

interface LeadCardProps {
  lead: FunnelLead;
  onOpen: (id: string) => void;
}

export function LeadCard({ lead, onOpen }: LeadCardProps) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: lead.id,
    data: { stage: lead.customer_state_now },
  });
  const style = transform ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)` } : undefined;
  const value = lead.contract_value || lead.quoted_amount;

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...listeners}
      {...attributes}
      onClick={() => onOpen(lead.id)}
      className={cn(
        "rounded-xl border border-border/60 bg-card p-3 cursor-grab active:cursor-grabbing touch-none select-none",
        "hover:border-primary/50 transition-colors space-y-2",
        isDragging && "opacity-60 ring-2 ring-primary/40 z-50"
      )}
    >
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
        <span className="flex items-center gap-1 text-muted-foreground shrink-0">
          <UserRound className="w-3 h-3" /> {OWNER_LABELS[lead.owner || "sdr"]}
        </span>
      </div>
    </div>
  );
}
