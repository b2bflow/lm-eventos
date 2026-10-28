import { useState, useEffect, useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { Sidebar } from "@/components/layout/Sidebar";
import { ConversationList, ConversationListItem } from "@/components/domain/chat/ConversationList";
import { ChatArea } from "@/components/domain/chat/ChatArea";
import { ClientProfile } from "@/components/domain/chat/ClientProfile";
import { EditLeadDialog } from "@/components/domain/crm/EditLeadDialog";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import api from "@/services/api";
import { socket } from "@/services/socket";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { normalizeChatMessageContent } from "@/lib/chatMessage";
import { CallDialog } from "@/components/domain/funnel/LeadDialogs";
import { quickRepliesFor, useLmSettings } from "@/hooks/useLmSettings";
import { useCurrentUser } from "@/hooks/useFunnel";
import { formatDateTime } from "@/lib/format";
import { formatChatListTime } from "@/lib/dateUtils";
import {
  appendMessageToCache,
  discardPendingConversationRefreshes,
  messagesKey,
  patchConversationInCache,
  refreshFirstConversationPages,
  removeConversationFromCache,
  useConversations,
  type ConversationsData,
  useMessages,
  type Conversa,
  type ConversationFilters,
  type ConversationTab,
  type NewMessageEvent,
} from "@/hooks/useConversations";

export type { Conversa };

function useDebounced<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

interface ContactSearchResult {
  customer: string;
  customer_name: string;
  customer_phone: string;
  customer_status: string;
  conversation: Conversa | null;
}

interface ChatMessage {
  id: string;
  content: string;
  created_at: string;
  direction?: string;
  role?: string;
  conversation_id?: string;
  conversation?: string;
  time?: string;
  [key: string]: unknown;
}

const CONTACT_PREFIX = "contact:";

export default function WhatsApp() {
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null);
  // Guarda a conversa aberta: ela pode sair da lista filtrada (busca/aba) sem fechar o chat.
  const [selectedSnapshot, setSelectedSnapshot] = useState<Conversa | null>(null);
  const [showFullHistory, setShowFullHistory] = useState(false);
  const [isProfileOpen, setIsProfileOpen] = useState(false);
  const [isEditLeadOpen, setIsEditLeadOpen] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [activeTab, setActiveTab] = useState<ConversationTab>("OPEN");
  const [searchInput, setSearchInput] = useState("");
  // Filtros da lista na URL (?atendimento=agente&responsavel=ia&qualificados=1): link e F5 mantêm a escolha
  const [searchParams, setSearchParams] = useSearchParams();
  const listFilters = useMemo<ConversationFilters>(() => {
    const attendance = ({ agente: "AGENTE", operador: "OPERADOR" } as const)[searchParams.get("atendimento") ?? ""];
    const assignee = searchParams.get("responsavel");
    return {
      ...(attendance ? { attendance } : {}),
      ...(assignee ? { assignee } : {}),
      ...(searchParams.get("qualificados") === "1" ? { aiQualified: true } : {}),
    };
  }, [searchParams]);
  const setListFilters = (filters: ConversationFilters) => {
    const params = new URLSearchParams(searchParams);
    const put = (key: string, value?: string) => (value ? params.set(key, value) : params.delete(key));
    put("atendimento", filters.attendance?.toLowerCase());
    put("responsavel", filters.assignee);
    put("qualificados", filters.aiQualified ? "1" : undefined);
    setSearchParams(params, { replace: true });
  };
  const [callOpen, setCallOpen] = useState(false);
  const [isCloseDialogOpen, setIsCloseDialogOpen] = useState(false);
  const [closeStatus, setCloseStatus] = useState<"WON" | "LOST">("WON");
  const [closeContractValue, setCloseContractValue] = useState("");
  const [closeNotes, setCloseNotes] = useState("");
  const [contactCandidates, setContactCandidates] = useState<ContactSearchResult[]>([]);
  const [startingCustomerId, setStartingCustomerId] = useState<string | null>(null);
  const { data: lmSettings } = useLmSettings();
  const { data: me } = useCurrentUser();
  const search = useDebounced(searchInput.trim(), 400);

  const queryClient = useQueryClient();

  const {
    conversations,
    isLoading: isLoadingConversations,
    fetchNextPage: fetchMoreConversations,
    hasNextPage: hasMoreConversations,
    isFetchingNextPage: isFetchingMoreConversations,
    internalFolder,
  } = useConversations(activeTab, search, listFilters);

  const selectedConversationObj =
    conversations.find((c) => c.id === selectedConversationId) ??
    (selectedSnapshot?.id === selectedConversationId ? selectedSnapshot : undefined);
  const isClosed = selectedConversationObj?.status === "CLOSED" || selectedConversationObj?.status === "ARCHIVED";

  useEffect(() => {
    const fresh = conversations.find((c) => c.id === selectedConversationId);
    if (fresh) setSelectedSnapshot(fresh);
  }, [conversations, selectedConversationId]);

  const {
    messages,
    fetchNextPage: fetchOlderMessages,
    hasNextPage: hasOlderMessages,
    isFetchingNextPage: isFetchingOlderMessages,
  } = useMessages(selectedConversationId, selectedConversationObj?.customer, showFullHistory);

  const markAsRead = useCallback(
    (id: string) => {
      patchConversationInCache(queryClient, id, { unread_count: 0, needs_attention: false });
      api.patch(`/chat/conversations/${id}/`, { mark_read: true });
    },
    [queryClient]
  );

  // A lista de conversas é atualizada pelo Sidebar (sobe a conversa para o topo);
  // aqui só entram as mensagens da conversa aberta.
  useEffect(() => {
    function onNewMessage(data: NewMessageEvent) {
      const convId = data.conversation_id || data.conversation;
      if (!convId) return;
      appendMessageToCache(queryClient, data);
      if (convId === selectedConversationId && data.direction === "INCOMING") {
        markAsRead(convId);
      }
    }
    socket.on("new_message", onNewMessage);
    return () => {
      socket.off("new_message", onNewMessage);
    };
  }, [queryClient, selectedConversationId, markAsRead]);

  const sendMessageMutation = useMutation({
    mutationFn: async ({ conversationId, message }: { conversationId: string; message: string }) => {
      await api.post("/chat/messages/", {
        conversation_id: conversationId,
        content: message,
      });
    },
    onMutate: () => setIsSending(true),
    onSettled: () => setIsSending(false),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: messagesKey(selectedConversationId, "conversation") });
    },
    onError: () => toast.error("Falha ao enviar mensagem."),
  });

  const sendFileMutation = useMutation({
    mutationFn: async ({ conversationId, file }: { conversationId: string; file: File }) => {
      const formData = new FormData();
      formData.append("conversation_id", conversationId);
      formData.append("file", file);
      await api.post("/chat/messages/files/", formData);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: messagesKey(selectedConversationId, "conversation") });
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
    },
    onError: (error) => apiError(error, "Falha ao enviar arquivo."),
  });

  // Contato sem conversa: a busca no backend não acha conversa, então procura o contato para iniciar uma.
  useEffect(() => {
    if (search.length < 2 || isLoadingConversations || conversations.length > 0) {
      setContactCandidates([]);
      return;
    }
    let cancelled = false;
    api
      .get("/chat/contacts/search/", { params: { search, status: activeTab === "CLOSED" ? "CLOSED" : "OPEN" } })
      .then(({ data }) => {
        if (cancelled) return;
        const results: ContactSearchResult[] = data.results || [];
        setContactCandidates(results.filter((result) => result.conversation === null));
      })
      .catch(() => {
        if (!cancelled) setContactCandidates([]);
      });
    return () => {
      cancelled = true;
    };
  }, [search, activeTab, isLoadingConversations, conversations.length]);

  /** Aplica a conversa devolvida pelo backend na lista e na conversa aberta. */
  const applyConversation = (updated: Conversa) => {
    patchConversationInCache(queryClient, updated.id, updated);
    setSelectedSnapshot((prev) => (prev && prev.id === updated.id ? { ...prev, ...updated } : prev));
    queryClient.invalidateQueries({ queryKey: messagesKey(updated.id, "conversation") });
  };

  const apiError = (error: unknown, fallback: string) =>
    toast.error((error as { response?: { data?: { detail?: string } } })?.response?.data?.detail || fallback);

  // Retomar IA / assumir: registra quem fez (mensagem interna e linha do tempo do card).
  const toggleTagMutation = useMutation({
    mutationFn: async ({ id, newTag }: { id: string; newTag: "AGENTE" | "OPERADOR" }) =>
      (await api.post<Conversa>(`/chat/conversations/${id}/mode/`, { mode: newTag })).data,
    onSuccess: (updated) => {
      toast.success(updated.tag === "AGENTE" ? "IA retomada nesta conversa." : "Você assumiu a conversa. IA pausada.");
      applyConversation(updated);
    },
    onError: (error) => apiError(error, "Não foi possível mudar o modo de atendimento."),
  });

  const assignMutation = useMutation({
    mutationFn: async ({ id, assignee }: { id: string; assignee: string | null }) =>
      (await api.post<Conversa>(`/chat/conversations/${id}/assign/`, { assignee })).data,
    onSuccess: (updated) => {
      toast.success("Responsável atualizado.");
      applyConversation(updated);
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
    },
    onError: (error) => apiError(error, "Não foi possível atribuir a conversa."),
  });

  // Chats internos: a conversa sai da lista em que está (principal ou pasta) e segue aberta pelo snapshot.
  const internalMutation = useMutation({
    mutationFn: async ({ id, internal }: { id: string; internal: boolean }) =>
      (await api.post<Conversa>(`/chat/conversations/${id}/internal/`, { internal })).data,
    onSuccess: (updated) => {
      toast.success(updated.customer_internal_chat
        ? "Conversa movida para os Chats internos."
        : "Conversa voltou para a lista principal.");
      applyConversation(updated);
      discardPendingConversationRefreshes();
      removeConversationFromCache(queryClient, updated.id);
      refreshFirstConversationPages(queryClient);
    },
    onError: (error) => apiError(error, "Não foi possível mover a conversa."),
  });

  const noteMutation = useMutation({
    mutationFn: async ({ id, text }: { id: string; text: string }) => {
      await api.post(`/chat/conversations/${id}/notes/`, { text });
      return id;
    },
    onSuccess: (id) => {
      toast.success("Nota interna salva.");
      queryClient.invalidateQueries({ queryKey: messagesKey(id, "conversation") });
    },
    onError: (error) => apiError(error, "Não foi possível salvar a nota."),
  });

  const callMutation = useMutation({
    mutationFn: async ({ id, outcome, notes }: { id: string; outcome: string; notes?: string }) => {
      await api.post(`/chat/conversations/${id}/calls/`, { outcome, notes });
      return id;
    },
    onSuccess: (id) => {
      toast.success("Ligação registrada.");
      queryClient.invalidateQueries({ queryKey: messagesKey(id, "conversation") });
    },
    onError: (error) => apiError(error, "Não foi possível registrar a ligação."),
  });

  /** Botão Ligar: abre o discador (tel:) e pede o resultado para a linha do tempo. */
  const handleCall = () => {
    const digits = (selectedConversationObj?.customer_phone || "").replace(/\D/g, "");
    if (digits) window.location.href = `tel:+${digits}`;
    setCallOpen(true);
  };

  const closeConversationMutation = useMutation({
    mutationFn: async ({ id, finalStatus, contractValue, notes }: { id: string, finalStatus: "WON" | "LOST", contractValue?: string, notes?: string }) => {
      await api.patch(`/chat/conversations/${id}/`, {
        status: "CLOSED",
        final_customer_status: finalStatus,
        contract_value: contractValue ? parseFloat(contractValue) : undefined,
        notes: notes || undefined,
      });
    },
    // Otimista: tira a conversa da lista na hora e descarta recargas em voo (react-query e polling)
    // que a trariam de volta. Listas ainda sem dados seguem carregando.
    onMutate: async ({ id }) => {
      discardPendingConversationRefreshes();
      await queryClient.cancelQueries({ queryKey: ["conversations"], predicate: (q) => q.state.data !== undefined });
      const previous = queryClient.getQueriesData<ConversationsData>({ queryKey: ["conversations"] });
      removeConversationFromCache(queryClient, id);
      return { previous };
    },
    onError: (error, _vars, context) => {
      context?.previous.forEach(([key, data]) => queryClient.setQueryData(key, data));
      apiError(error, "Não foi possível finalizar a conversa.");
    },
    onSuccess: () => {
      toast.success("Conversa finalizada!");
      queryClient.invalidateQueries({ queryKey: ["leads"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard-metrics"] });
      setIsCloseDialogOpen(false);
      setCloseStatus("WON");
      setCloseContractValue("");
      setCloseNotes("");
      setSelectedConversationId(null);
    },
    onSettled: () => refreshFirstConversationPages(queryClient),
  });

  const openConversationMutation = useMutation({
    mutationFn: async (id: string) => {
      await api.patch(`/chat/conversations/${id}/`, { status: "OPEN" });
      return id;
    },
    onSuccess: (id) => {
      toast.success("Conversa reaberta!");
      // Sai da lista de fechadas na hora; a conversa aberta segue pelo snapshot.
      setSelectedSnapshot((prev) => (prev && prev.id === id ? { ...prev, status: "OPEN" } : prev));
      discardPendingConversationRefreshes();
      removeConversationFromCache(queryClient, id);
      refreshFirstConversationPages(queryClient);
    },
    onError: (error) => apiError(error, "Não foi possível reabrir a conversa."),
  });

  const handleSendMessage = (message: string) => {
    if (selectedConversationId) {
      sendMessageMutation.mutate({ conversationId: selectedConversationId, message });
    }
  };

  const handleSendFile = (file: File) => {
    if (selectedConversationId) {
      sendFileMutation.mutate({ conversationId: selectedConversationId, file });
    }
  };

  const handleCloseConversation = () => {
    if (!selectedConversationId) return;
    closeConversationMutation.mutate({
      id: selectedConversationId,
      finalStatus: closeStatus,
      // Valor só vale para venda: não manda o que ficou digitado antes de trocar para "Perdido".
      contractValue: closeStatus === "WON" ? closeContractValue : undefined,
      notes: closeNotes,
    });
  };

  const handleToggleTag = (id: string, currentTag: string) => {
    if (id.startsWith(CONTACT_PREFIX)) return;
    const newTag = currentTag === "AGENTE" ? "OPERADOR" : "AGENTE";
    toggleTagMutation.mutate({ id, newTag });
  };

  const handleSelectConversation = (id: string) => {
    setSelectedConversationId(id);
    setShowFullHistory(false);
    const conv = conversations.find((c) => c.id === id);
    if (conv) {
      setSelectedSnapshot(conv);
    } else {
      // Conversa fora da lista carregada (ex.: conversa anterior aberta pelo perfil do cliente)
      api.get<Conversa>(`/chat/conversations/${id}/`)
        .then(({ data }) => setSelectedSnapshot(data))
        .catch(() => toast.error("Não foi possível abrir a conversa."));
    }

    setIsProfileOpen(false);
    markAsRead(id);
  };

  const handleSelectListItem = async (id: string) => {
    if (!id.startsWith(CONTACT_PREFIX)) {
      handleSelectConversation(id);
      return;
    }
    const customerId = id.slice(CONTACT_PREFIX.length);
    if (startingCustomerId === customerId) return;
    setStartingCustomerId(customerId);
    try {
      const { data } = await api.post<Conversa>("/chat/conversations/start/", { customer_id: customerId });
      setSelectedConversationId(data.id);
      setSelectedSnapshot(data);
      setShowFullHistory(false);
      setSearchInput("");
      setContactCandidates([]);
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
    } catch {
      toast.error("Não foi possível iniciar a conversa com este contato.");
    } finally {
      setStartingCustomerId(null);
    }
  };

  // Atalho vindo de outras páginas (ex.: Contatos): /whatsapp?conversa=<id>
  useEffect(() => {
    const id = searchParams.get("conversa");
    if (!id) return;
    handleSelectConversation(id);
    const params = new URLSearchParams(searchParams);
    params.delete("conversa");
    setSearchParams(params, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const listItems: ConversationListItem[] = useMemo(() => {
    const items: ConversationListItem[] = conversations.map((c: Conversa) => ({
      id: c.id,
      phone: c.customer_phone,
      name: c.customer_name,
      lastMessage: normalizeChatMessageContent(c.last_message_content),
      time: formatChatListTime(c.last_interaction_at),
      tag: c.tag as "AGENTE" | "OPERADOR",
      unread: (c.unread_count || 0) > 0,
      finished: c.status === "CLOSED" || c.status === "ARCHIVED",
      customer_status: c.final_customer_status || c.customer_status,
      needs_attention: c.needs_attention,
      assignee: c.assignee,
      aiQualified: !!c.customer_ai_qualified_at,
      internal: !!c.customer_internal_chat,
    }));
    contactCandidates.forEach((contact) =>
      items.push({
        id: `${CONTACT_PREFIX}${contact.customer}`,
        phone: contact.customer_phone,
        name: contact.customer_name,
        lastMessage: "Iniciar conversa com este contato",
        time: "",
        tag: "OPERADOR",
        unread: false,
        finished: false,
        customer_status: contact.customer_status,
      })
    );
    return items;
  }, [conversations, contactCandidates]);

  const handleLoadMoreConversations = useCallback(() => {
    if (hasMoreConversations && !isFetchingMoreConversations) fetchMoreConversations();
  }, [hasMoreConversations, isFetchingMoreConversations, fetchMoreConversations]);

  const handleLoadOlderMessages = useCallback(() => {
    if (hasOlderMessages && !isFetchingOlderMessages) fetchOlderMessages();
  }, [hasOlderMessages, isFetchingOlderMessages, fetchOlderMessages]);

  return (
    <div className="flex h-screen w-full bg-background overflow-hidden">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
        <main className="flex-1 p-0 md:p-6 overflow-hidden flex flex-col h-full">
          <div className="flex-1 glass md:rounded-2xl border-x-0 md:border border-border/50 overflow-hidden flex relative shadow-xl">

            <div className={cn(
              "w-full md:w-80 lg:w-96 flex-shrink-0 border-r border-border/50 transition-all duration-300",
              selectedConversationId ? "hidden md:flex flex-col" : "flex flex-col"
            )}>
              <ConversationList
                conversations={listItems}
                selectedId={selectedConversationId}
                onSelect={handleSelectListItem}
                onToggleTag={handleToggleTag}
                activeTab={activeTab}
                onTabChange={setActiveTab}
                internalFolder={internalFolder}
                search={searchInput}
                onSearchChange={setSearchInput}
                onLoadMore={handleLoadMoreConversations}
                filters={listFilters}
                onFiltersChange={setListFilters}
                hasMore={!!hasMoreConversations}
                isLoading={isLoadingConversations}
                isLoadingMore={isFetchingMoreConversations || !!startingCustomerId}
              />
            </div>

            <div className={cn(
              "flex-1 min-w-0 bg-background/50 transition-all duration-300",
              selectedConversationId ? "flex flex-col" : "hidden md:flex md:flex-col"
            )}>
              {selectedConversationId && selectedConversationObj ? (
                <ChatArea
                  key={`${selectedConversationId}-${showFullHistory ? "all" : "conv"}`}
                  conversationId={selectedConversationId}
                  conversationData={{ name: selectedConversationObj.customer_name || "Desconhecido", phone: selectedConversationObj.customer_phone || "Sem Número" }}
                  messages={messages}
                  onSendMessage={handleSendMessage}
                  onSendFile={handleSendFile}
                  isSending={isSending}
                  isUploadingFile={sendFileMutation.isPending}
                  isAIActive={selectedConversationObj.tag === "AGENTE"}
                  onToggleAI={(mode) => toggleTagMutation.mutate({ id: selectedConversationId, newTag: mode })}
                  aiBlocked={!!selectedConversationObj.customer_human_operator || !!selectedConversationObj.customer_internal_chat}
                  aiBlockedReason={selectedConversationObj.customer_internal_chat
                    ? "Chat interno não tem IA. Tire dos Chats internos para a IA atender."
                    : undefined}
                  isInternal={!!selectedConversationObj.customer_internal_chat}
                  onToggleInternal={() => internalMutation.mutate({
                    id: selectedConversationId,
                    internal: !selectedConversationObj.customer_internal_chat,
                  })}
                  handoverInfo={selectedConversationObj.handover_by_name
                    ? `${selectedConversationObj.tag === "AGENTE" ? "IA retomada" : "Assumida"} por ${selectedConversationObj.handover_by_name} em ${formatDateTime(selectedConversationObj.handover_at)}`
                    : undefined}
                  onAddNote={(text) => noteMutation.mutate({ id: selectedConversationId, text })}
                  onCall={handleCall}
                  quickReplies={quickRepliesFor(lmSettings, selectedConversationObj.customer_product,
                    selectedConversationObj.customer_name, me?.first_name || (lmSettings?.sdr_name as string) || "")}
                  isProfileOpen={isProfileOpen}
                  onToggleProfile={() => setIsProfileOpen(!isProfileOpen)}
                  onBack={() => setSelectedConversationId(null)}
                  isClosed={isClosed}
                  onCloseConversation={() => setIsCloseDialogOpen(true)}
                  onOpenConversation={() => openConversationMutation.mutate(selectedConversationId!)}
                  onLoadOlder={handleLoadOlderMessages}
                  hasOlder={!!hasOlderMessages}
                  isLoadingOlder={isFetchingOlderMessages}
                  onLoadHistory={() => setShowFullHistory(true)}
                  hasMoreHistory={!showFullHistory && (selectedConversationObj.past_conversations?.length ?? 0) > 0}
                />
              ) : (
                <div className="flex-1 flex items-center justify-center text-muted-foreground bg-background/50 h-full">
                  <p>Selecione uma conversa para iniciar o atendimento.</p>
                </div>
              )}
            </div>

          </div>
        </main>
      </div>

      {selectedConversationObj && (
        <ClientProfile
          open={isProfileOpen}
          onClose={() => setIsProfileOpen(false)}
          customer={{
              ...selectedConversationObj,
              id: selectedConversationObj.customer,
              conversation_id: selectedConversationObj.id
          }}
          onEdit={() => setIsEditLeadOpen(true)}
          onCloseConversation={() => setIsCloseDialogOpen(true)}
          isClosed={isClosed}
          onSelectConversation={handleSelectConversation}
          onAssign={(assignee) => assignMutation.mutate({ id: selectedConversationObj.id, assignee })}
          onCall={handleCall}
        />
      )}

      <CallDialog
        open={callOpen}
        onClose={() => setCallOpen(false)}
        onConfirm={(outcome, notes) => {
          setCallOpen(false);
          if (selectedConversationId) callMutation.mutate({ id: selectedConversationId, outcome, notes });
        }}
      />

      {selectedConversationObj && (
        <EditLeadDialog
          lead={{ ...selectedConversationObj, id: selectedConversationObj.customer }}
          isOpen={isEditLeadOpen}
          onClose={() => setIsEditLeadOpen(false)}
        />
      )}

      <Dialog open={isCloseDialogOpen} onOpenChange={setIsCloseDialogOpen}>
        <DialogContent className="glass border-border/50 sm:max-w-[460px]">
          <DialogHeader>
            <DialogTitle>Finalizar Atendimento</DialogTitle>
          </DialogHeader>

          <div className="space-y-4 py-2">
            <div className="grid grid-cols-2 gap-2">
              <Button
                type="button"
                variant={closeStatus === "WON" ? "default" : "outline"}
                onClick={() => setCloseStatus("WON")}
              >
                Venda
              </Button>
              <Button
                type="button"
                variant={closeStatus === "LOST" ? "default" : "outline"}
                onClick={() => setCloseStatus("LOST")}
              >
                Perdido
              </Button>
            </div>

            {closeStatus === "WON" && (
              <Input
                type="number"
                min="0"
                step="0.01"
                placeholder="Valor fechado"
                value={closeContractValue}
                onChange={(event) => setCloseContractValue(event.target.value)}
              />
            )}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setIsCloseDialogOpen(false)}>Cancelar</Button>
            <Button onClick={handleCloseConversation} disabled={closeConversationMutation.isPending}>
              Finalizar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
