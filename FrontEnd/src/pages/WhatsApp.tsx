import { useState, useEffect } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { ConversationList } from "@/components/domain/chat/ConversationList";
import { ChatArea } from "@/components/domain/chat/ChatArea";
import { ClientProfile } from "@/components/domain/chat/ClientProfile";
import { EditLeadDialog } from "@/components/domain/crm/EditLeadDialog";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api from "@/services/api";
import { socket } from "@/services/socket"; 
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { normalizeChatMessageContent } from "@/lib/chatMessage";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

export interface Conversa {
  final_customer_status?: string;
  past_conversations?: { id: string, created_at: string, status: string, final_customer_status?: string }[];
  past_quotes?: { id: string, created_at: string, status?: string, customer_state_now?: string, event_title?: string | null, quoted_amount?: number, contract_value?: number }[];
  id: string;
  customer: string; 
  quote_id?: string | null;
  customer_name: string; 
  customer_phone: string; 
  last_message_content: string;
  last_interaction_at: string;
  status: "OPEN" | "CLOSED" | "ARCHIVED";
  tag: string; 
  unread_count?: number;
  customer_status?: string;
  customer_state_now?: string;
  celebration_type?: string | null;
  event_title?: string | null;
  event_date?: string | null;
  guest_count?: number;
  quoted_amount?: number;
  contract_value?: number;
  venue?: string | null;
  notes?: string | null;
  next_step?: string | null;
  needs_attention?: boolean;
}

export default function WhatsApp() {
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null);
  const [showFullHistory, setShowFullHistory] = useState(false);
  const [isProfileOpen, setIsProfileOpen] = useState(false);
  const [isEditLeadOpen, setIsEditLeadOpen] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [isCloseDialogOpen, setIsCloseDialogOpen] = useState(false);
  const [closeStatus, setCloseStatus] = useState<"WON" | "LOST">("WON");
  const [closeContractValue, setCloseContractValue] = useState("");
  const [closeNotes, setCloseNotes] = useState("");

  const queryClient = useQueryClient();

  const { data: conversations = [], isLoading: isLoadingConversations } = useQuery<Conversa[]>({
    queryKey: ["conversations"],
    queryFn: async () => {
      const response = await api.get("/chat/conversations/");
      return response.data.results || response.data || []; 
    },
    refetchInterval: 30000, 
  });

  const selectedConversationObj = conversations.find(c => c.id === selectedConversationId);
  const isClosed = selectedConversationObj?.status === "CLOSED" || selectedConversationObj?.status === "ARCHIVED";

  const { data: messages = [], isLoading: isLoadingMessages, isFetching: isFetchingMessages } = useQuery({
    queryKey: ["messages", selectedConversationId, showFullHistory],
    queryFn: async () => {
      if (!selectedConversationId) return [];
      
      let url = `/chat/messages/?conversation=${selectedConversationId}`;
      if (showFullHistory && selectedConversationObj?.customer) {
        url = `/chat/messages/?customer=${selectedConversationObj.customer}`;
      }

      const response = await api.get(url);
      const msgs = response.data.results || response.data || [];
      return msgs.map((msg: any) => ({
        id: msg.id,
        content: normalizeChatMessageContent(msg.content),
        direction: msg.direction,
        role: msg.role,
        created_at: msg.created_at,
        time: msg.created_at ? new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : "",
        conversation: msg.conversation_id || msg.conversation
      }));
    },
    enabled: !!selectedConversationId,
  });

  const markAsReadMutation = useMutation({
    mutationFn: async (id: string) => {
      await api.patch(`/chat/conversations/${id}/`, { mark_read: true });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
    }
  });

  useEffect(() => {
    socket.on("new_message", (data) => {
      const convId = data.conversation_id || data.conversation;
      
      if (!convId) return;

      queryClient.setQueryData(["messages", convId, showFullHistory], (oldMessages: any) => {
        if (!oldMessages) return [data];
        const exists = oldMessages.some((m: any) => String(m.id) === String(data.id));
        if (exists) return oldMessages;
        return [...oldMessages, {
          ...data,
          content: normalizeChatMessageContent(data.content),
          time: new Date(data.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        }];
      });      
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
      if (convId === selectedConversationId) {
        markAsReadMutation.mutate(convId);
      }
    });

    return () => {
      socket.off("new_message");
    };
  }, [queryClient, selectedConversationId, showFullHistory, markAsReadMutation]);

  const sendMessageMutation = useMutation({
    mutationFn: async ({ conversationId, message }: { conversationId: string, message: string }) => {
      await api.post('/chat/messages/', {
        conversation_id: conversationId,
        content: message
      });
    },
    onMutate: () => setIsSending(true),
    onSettled: () => setIsSending(false),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["messages", selectedConversationId, showFullHistory] });
    },
    onError: () => toast.error("Falha ao enviar mensagem.")
  });

  const toggleTagMutation = useMutation({
    mutationFn: async ({ id, newTag }: { id: string, newTag: string }) => {
      await api.patch(`/chat/conversations/${id}/`, { tag: newTag });
    },
    onSuccess: () => {
      toast.success("Modo de atendimento alterado!");
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
    }
  });

  const closeConversationMutation = useMutation({
    mutationFn: async ({ id, finalStatus, contractValue, notes }: { id: string, finalStatus: "WON" | "LOST", contractValue?: string, notes?: string }) => {
      await api.patch(`/chat/conversations/${id}/`, {
        status: "CLOSED",
        final_customer_status: finalStatus,
        contract_value: contractValue ? parseFloat(contractValue) : undefined,
        notes: notes || undefined,
      });
    },
    onSuccess: () => {
      toast.success("Conversa finalizada!");
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
      queryClient.invalidateQueries({ queryKey: ["leads"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard-metrics"] });
      setIsCloseDialogOpen(false);
      setSelectedConversationId(null);
      setCloseContractValue("");
      setCloseNotes("");
    }
  });

  const openConversationMutation = useMutation({
    mutationFn: async (id: string) => {
      await api.patch(`/chat/conversations/${id}/`, { status: "OPEN" });
    },
    onSuccess: () => {
      toast.success("Conversa reaberta!");
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
    }
  });

  const handleSendMessage = (message: string) => {
    if (selectedConversationId) {
      sendMessageMutation.mutate({ conversationId: selectedConversationId, message });
    }
  };

  const handleToggleTag = (id: string, currentTag: string) => {
    const newTag = currentTag === "AGENTE" ? "OPERADOR" : "AGENTE";
    toggleTagMutation.mutate({ id, newTag });
  };

  const handleSelectConversation = (id: string) => {
    setSelectedConversationId(id);
    setShowFullHistory(false);
    
    if (window.innerWidth < 1024) {
      setIsProfileOpen(false);
    }
    queryClient.setQueryData(["conversations"], (old: any) => {
      if (!old || !old.results) return old;
      return {
        ...old,
        results: old.results.map((c: any) =>
          c.id === id ? { ...c, unread_count: 0, needs_attention: false } : c
        ),
      };
    });
    api.patch(`/chat/conversations/${id}/`, { mark_read: true });   
    api.patch(`/chat/conversations/${id}/`, { needs_attention: false });
  };

  const handleCloseConversation = () => {
    if (!selectedConversationId) return;
    closeConversationMutation.mutate({
      id: selectedConversationId,
      finalStatus: closeStatus,
      contractValue: closeContractValue,
      notes: closeNotes,
    });
  };

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
                conversations={conversations.map((c: Conversa) => ({
                  id: c.id,
                  phone: c.customer_phone,
                  name: c.customer_name,
                  lastMessage: normalizeChatMessageContent(c.last_message_content),
                  time: c.last_interaction_at ? new Date(c.last_interaction_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : "",
                  tag: c.tag,
                  unread: (c.unread_count || 0) > 0,
                  finished: c.status === "CLOSED",
                  customer_status: c.final_customer_status || c.customer_status,
                  needs_attention: c.needs_attention 
                }))}
                selectedId={selectedConversationId}
                onSelect={handleSelectConversation}
                onToggleTag={handleToggleTag}
              />
            </div>

            <div className={cn(
              "flex-1 min-w-0 bg-background/50 transition-all duration-300",
              selectedConversationId && !isProfileOpen ? "flex flex-col" : "hidden",
              !isProfileOpen ? "md:flex md:flex-col" : "md:hidden",
              "lg:flex lg:flex-col"
            )}>
              {selectedConversationId && selectedConversationObj ? (
                <ChatArea 
                  conversationId={selectedConversationId}
                  conversationData={{ name: selectedConversationObj.customer_name || "Desconhecido", phone: selectedConversationObj.customer_phone || "Sem Número" }}
                  messages={messages}
                  onSendMessage={handleSendMessage}
                  isSending={isSending}
                  isAIActive={selectedConversationObj.tag === "AGENTE"}
                  onToggleAI={(mode) => handleToggleTag(selectedConversationId, mode === "AGENTE" ? "OPERADOR" : "AGENTE")}
                  isProfileOpen={isProfileOpen}
                  onToggleProfile={() => setIsProfileOpen(!isProfileOpen)}
                  onBack={() => setSelectedConversationId(null)}
                  isClosed={isClosed}
                  onCloseConversation={() => setIsCloseDialogOpen(true)}
                  onOpenConversation={() => openConversationMutation.mutate(selectedConversationId!)} 
                  onLoadHistory={() => setShowFullHistory(true)}
                  isLoadingHistory={isFetchingMessages && showFullHistory} 
                  hasMoreHistory={!showFullHistory} 
                />
              ) : (
                <div className="flex-1 flex items-center justify-center text-muted-foreground bg-background/50 h-full">
                  <p>Selecione uma conversa para iniciar o atendimento.</p>
                </div>
              )}
            </div>

            {selectedConversationObj && isProfileOpen && (
              <div className={cn(
                  "flex-shrink-0 border-l border-border/50 bg-background/50 animate-in slide-in-from-right-10 duration-300",
                  isProfileOpen ? "block md:flex md:flex-col" : "hidden",
                  "w-full md:w-auto md:flex-1 lg:flex-none lg:w-80"
              )}>
                <ClientProfile 
                  customer={{ 
                      ...selectedConversationObj,
                      id: selectedConversationObj.customer, 
                      conversation_id: selectedConversationObj.id
                  }} 
                  onEdit={() => setIsEditLeadOpen(true)}
                  onCloseMobile={() => setIsProfileOpen(false)}
                  onCloseConversation={() => setIsCloseDialogOpen(true)}
                  isClosed={isClosed}
                  onSelectConversation={handleSelectConversation} 
                />
              </div>
            )}
          </div>
        </main>
      </div>

      {selectedConversationObj && (
        <EditLeadDialog 
          lead={{
            ...selectedConversationObj,
            id: selectedConversationObj.customer,
            quote_id: selectedConversationObj.quote_id || undefined,
            name: selectedConversationObj.customer_name,
            phone: selectedConversationObj.customer_phone,
          }}
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

            <Textarea
              rows={4}
              placeholder="Observação de fechamento"
              value={closeNotes}
              onChange={(event) => setCloseNotes(event.target.value)}
            />
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
