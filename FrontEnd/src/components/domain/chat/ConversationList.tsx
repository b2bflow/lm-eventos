import { useEffect, useRef } from "react";
import { MessageSquare, Sparkles, User, CheckCircle2, Clock, Search, Loader2 } from "lucide-react";
import { Input } from "@/components/ui/input";
import { LEAD_STATUS_LABELS, LEAD_STATUS_SOLID, OWNER_LABELS, resolveStage } from "@/constants/mappings";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const ALL_ASSIGNEES = "__all__";
import { cn } from "@/lib/utils";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";

interface Conversation {
  id: string;
  phone: string;
  name: string;
  lastMessage: string;
  time: string;
  tag: "AGENTE" | "OPERADOR"; 
  unread?: boolean;
  finished?: boolean;
  customer_status?: string;
  needs_attention?: boolean;
  assignee?: string | null;
}

export type ConversationListItem = Conversation;

interface ConversationListProps {
  conversations: Conversation[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onToggleTag?: (id: string, currentTag: "AGENTE" | "OPERADOR") => void;
  activeTab: "OPEN" | "CLOSED";
  onTabChange: (tab: "OPEN" | "CLOSED") => void;
  search: string;
  onSearchChange: (value: string) => void;
  onLoadMore: () => void;
  hasMore: boolean;
  isLoading?: boolean;
  isLoadingMore?: boolean;
  /** Filtro por responsável: "" (todas), sdr, erica, lucia ou none (sem responsável). */
  assignee?: string;
  onAssigneeChange?: (value: string) => void;
}

const getStatusDisplay = (status: string | undefined) => {
  const stage = resolveStage(status);
  return { label: LEAD_STATUS_LABELS[stage], color: LEAD_STATUS_SOLID[stage] };
};

export function ConversationList({
  conversations, selectedId, onSelect, onToggleTag,
  activeTab, onTabChange, search, onSearchChange,
  onLoadMore, hasMore, isLoading, isLoadingMore, assignee = "", onAssigneeChange,
}: ConversationListProps) {
  // A aba e a busca são filtradas no backend; a lista já chega filtrada e paginada.
  const filteredConversations = conversations;
  const scrollRef = useRef<HTMLDivElement>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel || !hasMore) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting && !isLoadingMore) onLoadMore();
      },
      { root: scrollRef.current, rootMargin: "200px" }
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [hasMore, isLoadingMore, onLoadMore, conversations.length]);

  return (
    <div className="h-full flex flex-col bg-background/50 backdrop-blur-xl border-r border-border/50">
      <div className="p-5 border-b border-border/50 flex-shrink-0">
        <h2 className="text-xl font-semibold text-foreground flex items-center gap-2">
          <MessageSquare className="w-5 h-5 text-primary" />
          Conversas
        </h2>

        <div className="flex gap-2 mt-4 p-1 bg-secondary/50 rounded-lg">
          <button
            onClick={() => onTabChange("OPEN")}
            className={cn(
              "flex-1 py-1.5 text-xs font-bold rounded-md transition-all",
              activeTab === "OPEN" ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
            )}
          >
            Abertas
          </button>
          <button
            onClick={() => onTabChange("CLOSED")}
            className={cn(
              "flex-1 py-1.5 text-xs font-bold rounded-md transition-all",
              activeTab === "CLOSED" ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
            )}
          >
            Fechadas
          </button>
        </div>

        <div className="relative mt-3">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Buscar por nome ou telefone"
            className="pl-9 h-9 text-sm bg-card/50"
          />
        </div>

        {onAssigneeChange && (
          <Select value={assignee || ALL_ASSIGNEES} onValueChange={(v) => onAssigneeChange(v === ALL_ASSIGNEES ? "" : v)}>
            <SelectTrigger className="h-9 mt-2 text-sm bg-card/50"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL_ASSIGNEES}>Todos os responsáveis</SelectItem>
              {Object.entries(OWNER_LABELS).map(([key, label]) => <SelectItem key={key} value={key}>{label}</SelectItem>)}
              <SelectItem value="none">Sem responsável</SelectItem>
            </SelectContent>
          </Select>
        )}
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto scrollbar-thin p-3 space-y-2">
        {isLoading ? (
          <div className="flex justify-center py-10 text-muted-foreground">
            <Loader2 className="w-6 h-6 animate-spin" />
          </div>
        ) : filteredConversations.length === 0 ? (
          <div className="text-center py-10 text-muted-foreground">
            <CheckCircle2 className="w-10 h-10 mx-auto mb-3 opacity-20" />
            <p className="text-sm">Nenhuma conversa encontrada</p>
          </div>
        ) : (
          filteredConversations.map((conv) => {
            const statusInfo = getStatusDisplay(conv.customer_status);

            return (
              <div
                key={conv.id}
                onClick={() => onSelect(conv.id)}
                className={cn(
                  "p-3 rounded-xl cursor-pointer transition-all group border",
                  selectedId === conv.id
                    ? "bg-primary/10 border-primary/30 shadow-sm"
                    : "bg-card/50 border-transparent hover:bg-card hover:border-border/50"
                )}
              >
                <div className="flex items-start gap-3">
                  <Avatar className={cn(
                    "w-10 h-10 border transition-transform shrink-0", 
                    selectedId === conv.id ? "border-primary" : "border-border/50 group-hover:scale-105"
                  )}>
                    <AvatarFallback className={cn(
                      "font-bold",
                      selectedId === conv.id ? "bg-primary text-primary-foreground" : "bg-secondary text-secondary-foreground"
                    )}>
                      {conv.name.substring(0, 2).toUpperCase()}
                    </AvatarFallback>
                  </Avatar>
                  
                  <div className="flex-1 min-w-0 flex flex-col">
                    {/* LINHA SUPERIOR: Nome (Esquerda) e Notificação (Direita) */}
                    <div className="flex justify-between items-start mb-0.5">
                      <h3 className="text-sm font-bold text-foreground truncate pr-2">
                        {conv.name}
                      </h3>
                      <div className="shrink-0 pt-1">
                        {conv.needs_attention && !conv.finished && selectedId !== conv.id ? (
                          <div className="w-2.5 h-2.5 bg-amber-500 rounded-full shadow-[0_0_8px_rgba(245,158,11,0.6)] animate-pulse" title="Transferido pela IA" />
                        ) : conv.unread && !conv.finished && selectedId !== conv.id ? (
                          <div className="w-2.5 h-2.5 bg-primary rounded-full shadow-[0_0_8px_rgba(var(--primary),0.5)] animate-pulse" title="Nova mensagem" />
                        ) : null}
                      </div>
                    </div>

                    {/* MENSAGEM DO MEIO */}
                    <p className="text-xs text-muted-foreground truncate mb-2">
                      {conv.lastMessage || "Nenhuma mensagem"}
                    </p>

                    {/* LINHA INFERIOR: Tags (Esquerda) e Horário (Direita) */}
                    <div className="flex items-end justify-between gap-2 mt-auto">
                      <div className="flex flex-wrap items-center gap-2">
                        {!conv.finished && (
                          <>
                            <button
                              onClick={(e) => {
                                e.stopPropagation(); 
                                onToggleTag?.(conv.id, conv.tag);
                              }}
                              className={cn(
                                "flex items-center gap-1.5 px-3 py-1 rounded-full text-[10px] font-bold transition-all border shadow-sm hover:scale-105 active:scale-95",
                                conv.tag === "AGENTE" 
                                  ? "bg-purple-500 text-white border-purple-400 hover:bg-purple-600 shadow-purple-500/20" 
                                  : "bg-blue-600 text-white border-blue-500 hover:bg-blue-700 shadow-blue-600/20"
                              )}
                            >
                              {conv.tag === "AGENTE" ? (
                                <><Sparkles className="w-3 h-3 animate-pulse" />AGENTE IA</>
                              ) : (
                                <><User className="w-3 h-3" />OPERADOR</>
                              )}
                            </button>

                            <div className={cn(
                              "flex items-center gap-1.5 px-3 py-1 rounded-full text-[10px] font-bold border shadow-sm",
                              statusInfo.color
                            )}>
                              {statusInfo.label}
                            </div>
                            {conv.assignee && (
                              <span className="px-2 py-1 rounded-full text-[10px] font-bold border border-border/60 text-muted-foreground">
                                {OWNER_LABELS[conv.assignee] || conv.assignee}
                              </span>
                            )}
                          </>
                        )}
                      </div>

                      {/* Horário forçado na ponta inferior direita */}
                      <span className="text-[10px] text-muted-foreground font-medium flex items-center gap-1 shrink-0 ml-auto pb-0.5">
                        <Clock className="w-3 h-3" />
                        {conv.time}
                      </span>
                    </div>

                  </div>
                </div>
              </div>
            );
          })
        )}
        {hasMore && (
          <div ref={sentinelRef} className="flex justify-center py-3 text-muted-foreground">
            {isLoadingMore && <Loader2 className="w-4 h-4 animate-spin" />}
          </div>
        )}
      </div>
    </div>
  );
}
