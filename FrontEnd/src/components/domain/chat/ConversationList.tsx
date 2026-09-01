import { useEffect, useMemo, useRef, useState } from "react";
import { MessageSquare, Sparkles, User, CheckCircle2, Clock, Tag, Search, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  CUSTOMER_TAG_LABELS,
  CUSTOMER_TAG_OPTIONS,
  CUSTOMER_TAG_STYLES,
  LEAD_STATUS_LABELS,
  LEAD_STATUS_OPTIONS,
} from "@/constants/mappings";

export interface ConversationListItem {
  id: string;
  customerId: string;
  phone: string;
  name: string;
  lastMessage: string;
  time: string;
  tag: string;
  ai_active?: boolean;
  unread?: boolean;
  finished?: boolean;
  customer_status?: string;
  customer_custom_tag?: string | null;
  needs_attention?: boolean; 
  contactOnly?: boolean;
}

interface ConversationListProps {
  conversations: ConversationListItem[];
  selectedId: string | null;
  onSelect: (conversation: ConversationListItem) => void;
  onToggleTag?: (id: string, currentTag: string) => void;
  onRemoteSearch: (term: string, status: "OPEN" | "CLOSED") => Promise<void>;
  isRemoteSearching?: boolean;
  remoteSearchError?: boolean;
}

const getStatusDisplay = (status: string | undefined) => {
  switch(status) {
    case 'ANALYSIS': return { label: 'Análise', color: 'bg-slate-600 text-white border-slate-500 shadow-slate-500/20' };
    case 'BUDGET': return { label: 'Orçamento Enviado', color: 'bg-amber-500 text-white border-amber-400 shadow-amber-500/20' };
    case 'NEGOTIATING': return { label: 'Negociando', color: 'bg-sky-500 text-white border-sky-400 shadow-sky-500/20' };
    case 'WAITING_BUDGET': return { label: 'Orçamento Pendente', color: 'text-yellow-600 bg-yellow-500/10 border-yellow-500/20' };
    case 'WON': return { label: 'Venda', color: 'bg-emerald-500 text-white border-emerald-400 shadow-emerald-500/20' };
    case 'LOST': return { label: 'Perdido', color: 'bg-rose-500 text-white border-rose-400 shadow-rose-500/20' };
    default: return { label: 'Análise', color: 'bg-slate-600 text-white border-slate-500 shadow-slate-500/20' };
  }
};

const normalizeSearch = (value?: string | null) => (value || "")
  .normalize("NFD")
  .replace(/[\u0300-\u036f]/g, "")
  .toLowerCase()
  .trim();

export function ConversationList({
  conversations,
  selectedId,
  onSelect,
  onToggleTag,
  onRemoteSearch,
  isRemoteSearching = false,
  remoteSearchError = false,
}: ConversationListProps) {
  const [activeTab, setActiveTab] = useState<"OPEN" | "CLOSED">("OPEN");
  const [modeFilter, setModeFilter] = useState<"all" | "ai" | "manual">("all");
  const [customTagFilter, setCustomTagFilter] = useState<string>("all");
  const [searchTerm, setSearchTerm] = useState("");
  const lastRemoteSearch = useRef("");

  const normalizedTerm = normalizeSearch(searchTerm);
  const phoneTerm = (searchTerm || "").replace(/\D/g, "");
  const isAiMode = (conversation: ConversationListItem) =>
    conversation.tag === "AGENTE" && conversation.ai_active === true;

  const filteredConversations = useMemo(() => conversations.filter((conversation) => {
    const belongsToTab = activeTab === "OPEN" ? !conversation.finished : conversation.finished;
    const belongsToMode = modeFilter === "all"
      || (modeFilter === "ai" && isAiMode(conversation))
      || (modeFilter === "manual" && !isAiMode(conversation));
    const matchesCustomTag =
      customTagFilter === "all" ||
      conversation.customer_status === customTagFilter ||
      conversation.customer_custom_tag === customTagFilter;

    if (!belongsToTab || !belongsToMode || !matchesCustomTag || (conversation.contactOnly && normalizedTerm.length < 2)) return false;
    if (!normalizedTerm) return true;

    const nameMatches = normalizeSearch(conversation.name).includes(normalizedTerm);
    const normalizedPhone = (conversation.phone || "").replace(/\D/g, "");
    const phoneMatches = phoneTerm.length > 0 && normalizedPhone.includes(phoneTerm);
    return nameMatches || phoneMatches;
  }), [activeTab, conversations, modeFilter, customTagFilter, normalizedTerm, phoneTerm]);

  const getModeLabel = (isActive: boolean) => isActive ? "AGENTE IA ATIVO" : "OPERADOR MANUAL";
  const getModeStyle = (isActive: boolean) => isActive
    ? "bg-purple-500 text-white border-purple-400 hover:bg-purple-600 shadow-purple-500/20"
    : "bg-blue-600 text-white border-blue-500 hover:bg-blue-700 shadow-blue-600/20";

  useEffect(() => {
    if (normalizedTerm.length < 2 || filteredConversations.length > 0) return;

    const searchKey = `${activeTab}:${normalizedTerm}`;
    if (lastRemoteSearch.current === searchKey) return;

    const timeoutId = window.setTimeout(() => {
      lastRemoteSearch.current = searchKey;
      void onRemoteSearch(searchTerm.trim(), activeTab);
    }, 300);

    return () => window.clearTimeout(timeoutId);
  }, [activeTab, filteredConversations.length, normalizedTerm, onRemoteSearch, searchTerm]);

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
              value={modeFilter}
              onChange={(event) => setModeFilter(event.target.value as "all" | "ai" | "manual")}
              className="h-8 w-full rounded-md border border-border/50 bg-background px-2 text-xs font-medium text-foreground outline-none focus:border-primary"
            >
              <option value="all">Todos os modos</option>
              <option value="ai">Agente IA Ativo</option>
              <option value="manual">Operador Manual</option>
            </select>
          </div>

          <div className="flex items-center gap-2">
            <Tag className="w-4 h-4 text-muted-foreground" />
            <select
              value={customTagFilter}
              onChange={(event) => setCustomTagFilter(event.target.value)}
              className="h-8 w-full rounded-md border border-border/50 bg-background px-2 text-xs font-medium text-foreground outline-none focus:border-primary"
            >
              <option value="all">Filtrar por tag</option>
              {LEAD_STATUS_OPTIONS.map((status) => (
                <option key={status} value={status}>
                  {LEAD_STATUS_LABELS[status] || status}
                </option>
              ))}
              <option value="visita tecnica">
                {CUSTOMER_TAG_LABELS["visita tecnica"] || "Visita técnica"}
              </option>
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

        <div className="relative mt-3">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            type="search"
            value={searchTerm}
            onChange={(event) => setSearchTerm(event.target.value)}
            placeholder="Buscar por nome ou telefone"
            className="h-10 w-full rounded-lg border border-border/60 bg-background/70 pl-9 pr-9 text-sm outline-none transition-colors placeholder:text-muted-foreground focus:border-primary/60"
          />
          {isRemoteSearching && (
            <Loader2 className="absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 animate-spin text-primary" />
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto scrollbar-thin p-3 space-y-2">
        {filteredConversations.length === 0 ? (
          <div className="text-center py-10 text-muted-foreground">
            <CheckCircle2 className="w-10 h-10 mx-auto mb-3 opacity-20" />
            <p className="text-sm">
              {remoteSearchError ? "Não foi possível buscar no banco" : isRemoteSearching ? "Buscando contatos..." : "Nenhuma conversa encontrada"}
            </p>
          </div>
        ) : (
          filteredConversations.map((conv) => {
            const statusInfo = getStatusDisplay(conv.customer_status);
            const aiMode = isAiMode(conv);

            return (
              <div
                key={conv.id}
                onClick={() => onSelect(conv)}
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
                      {(conv.name || "Desconhecido").substring(0, 2).toUpperCase()}
                    </AvatarFallback>
                  </Avatar>
                  
                  <div className="flex-1 min-w-0 flex flex-col">
                    {/* LINHA SUPERIOR: Nome (Esquerda) e Notificação (Direita) */}
                    <div className="flex justify-between items-start mb-0.5">
                      <h3 className="text-sm font-bold text-foreground truncate pr-2">
                        {conv.name || "Desconhecido"}
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
                      <div className="flex min-w-0 flex-col items-start gap-1.5">
                        {!conv.finished && !conv.contactOnly && (
                          <>
                            <button
                              onClick={(e) => {
                                e.stopPropagation(); 
                                onToggleTag?.(conv.id, aiMode ? "AGENTE" : "OPERADOR");
                              }}
                              className={cn(
                                "flex items-center gap-1.5 px-3 py-1 rounded-full text-[10px] font-bold transition-all border shadow-sm hover:scale-105 active:scale-95",
                                getModeStyle(aiMode)
                              )}
                            >
                              {aiMode ? (
                                <><Sparkles className="w-3 h-3 animate-pulse" />{getModeLabel(aiMode)}</>
                              ) : (
                                <><User className="w-3 h-3" />{getModeLabel(aiMode)}</>
                              )}
                            </button>

                            <div className="flex min-w-0 flex-wrap items-center gap-1.5">
                              <div className={cn(
                                "flex items-center gap-1.5 px-3 py-1 rounded-full text-[10px] font-bold border shadow-sm",
                                statusInfo.color
                              )}>
                                {statusInfo.label}
                              </div>

                              {conv.customer_custom_tag && (
                                <div className={cn(
                                  "flex items-center gap-1.5 px-3 py-1 rounded-full text-[10px] font-bold border shadow-sm",
                                  CUSTOMER_TAG_STYLES[conv.customer_custom_tag] || "bg-secondary text-secondary-foreground border-border"
                                )}>
                                  {CUSTOMER_TAG_LABELS[conv.customer_custom_tag] || conv.customer_custom_tag}
                                </div>
                              )}
                            </div>
                          </>
                        )}
                        {conv.contactOnly && (
                          <div className="rounded-full border border-primary/30 bg-primary/10 px-3 py-1 text-[10px] font-bold text-primary">
                            INICIAR CONVERSA
                          </div>
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
