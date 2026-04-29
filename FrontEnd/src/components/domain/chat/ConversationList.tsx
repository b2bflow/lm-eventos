import { useState } from "react";
import { MessageSquare, Sparkles, User, CheckCircle2, Clock, Tag } from "lucide-react";
import { cn } from "@/lib/utils";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";

interface Conversation {
  id: string;
  phone: string;
  name: string;
  lastMessage: string;
  time: string;
  tag: string; 
  unread?: boolean;
  finished?: boolean;
  customer_status?: string;
  needs_attention?: boolean; 
}

interface ConversationListProps {
  conversations: Conversation[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onToggleTag?: (id: string, currentTag: string) => void;
}

const getStatusDisplay = (status: string | undefined) => {
  switch(status) {
    case 'ANALYSIS': return { label: 'Análise', color: 'bg-slate-600 text-white border-slate-500 shadow-slate-500/20' };
    case 'BUDGET': return { label: 'Orçamento', color: 'bg-amber-500 text-white border-amber-400 shadow-amber-500/20' };
    case 'NEGOTIATING': return { label: 'Negociando', color: 'bg-sky-500 text-white border-sky-400 shadow-sky-500/20' };
    case 'WON': return { label: 'Venda', color: 'bg-emerald-500 text-white border-emerald-400 shadow-emerald-500/20' };
    case 'LOST': return { label: 'Perdido', color: 'bg-rose-500 text-white border-rose-400 shadow-rose-500/20' };
    default: return { label: 'Análise', color: 'bg-slate-600 text-white border-slate-500 shadow-slate-500/20' };
  }
};

export function ConversationList({ conversations, selectedId, onSelect, onToggleTag }: ConversationListProps) {
  const [activeTab, setActiveTab] = useState<"OPEN" | "CLOSED">("OPEN");
  const [tagFilter, setTagFilter] = useState<string>("all");

  const availableTags = Array.from(new Set(conversations.map((c) => c.tag).filter(Boolean))).sort();

  const filteredConversations = conversations.filter(c => {
    const matchesStatus = activeTab === "OPEN" ? !c.finished : c.finished;
    const matchesTag = tagFilter === "all" || c.tag === tagFilter;
    return matchesStatus && matchesTag;
  });

  const getTagLabel = (tag: string) => {
    switch (tag) {
      case "AGENTE": return "AGENTE IA";
      case "OPERADOR": return "OPERADOR";
      case "operador_humano": return "OPERADOR HUMANO";
      case "orcamento": return "ORÇAMENTO";
      default: return tag.replace(/_/g, " ").toUpperCase();
    }
  };

  const getTagStyle = (tag: string) => {
    switch (tag) {
      case "AGENTE": return "bg-purple-500 text-white border-purple-400 hover:bg-purple-600 shadow-purple-500/20";
      case "orcamento": return "bg-amber-500 text-white border-amber-400 hover:bg-amber-600 shadow-amber-500/20";
      case "operador_humano": return "bg-emerald-600 text-white border-emerald-500 hover:bg-emerald-700 shadow-emerald-600/20";
      default: return "bg-blue-600 text-white border-blue-500 hover:bg-blue-700 shadow-blue-600/20";
    }
  };

  return (
    <div className="h-full flex flex-col bg-background/50 backdrop-blur-xl border-r border-border/50">
      <div className="p-5 border-b border-border/50 flex-shrink-0">
        <h2 className="text-xl font-semibold text-foreground flex items-center gap-2">
          <MessageSquare className="w-5 h-5 text-primary" />
          Conversas
        </h2>

        <div className="mt-4 space-y-2">
          <div className="flex items-center gap-2">
            <Tag className="w-4 h-4 text-muted-foreground" />
            <select
              value={tagFilter}
              onChange={(event) => setTagFilter(event.target.value)}
              className="h-8 w-full rounded-md border border-border/50 bg-background px-2 text-xs font-medium text-foreground outline-none focus:border-primary"
            >
              <option value="all">Todas as tags</option>
              {availableTags.map((tag) => (
                <option key={tag} value={tag}>{getTagLabel(tag)}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="flex gap-2 mt-3 p-1 bg-secondary/50 rounded-lg">
          <button
            onClick={() => setActiveTab("OPEN")}
            className={cn(
              "flex-1 py-1.5 text-xs font-bold rounded-md transition-all",
              activeTab === "OPEN" ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
            )}
          >
            Abertas
          </button>
          <button
            onClick={() => setActiveTab("CLOSED")}
            className={cn(
              "flex-1 py-1.5 text-xs font-bold rounded-md transition-all",
              activeTab === "CLOSED" ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
            )}
          >
            Fechadas
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto scrollbar-thin p-3 space-y-2">
        {filteredConversations.length === 0 ? (
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
                                getTagStyle(conv.tag)
                              )}
                            >
                              {conv.tag === "AGENTE" ? (
                                <><Sparkles className="w-3 h-3 animate-pulse" />AGENTE IA</>
                              ) : (
                                <><User className="w-3 h-3" />{getTagLabel(conv.tag)}</>
                              )}
                            </button>

                            <div className={cn(
                              "flex items-center gap-1.5 px-3 py-1 rounded-full text-[10px] font-bold border shadow-sm",
                              statusInfo.color
                            )}>
                              {statusInfo.label}
                            </div>
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
      </div>
    </div>
  );
}
