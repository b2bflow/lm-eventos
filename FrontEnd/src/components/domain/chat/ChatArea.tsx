import { Send, Paperclip, Loader2, MoreVertical, Sparkles, User, CheckCircle, ArrowLeft, History } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useState, useRef, useEffect } from "react";
import { cn } from "@/lib/utils";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { format, isToday, isYesterday, differenceInDays } from "date-fns";
import { ptBR } from "date-fns/locale";

export interface Message {
    id: string;
    content: string;
    direction: "INCOMING" | "OUTGOING";
    role: string;
    created_at: string; 
    time: string; 
    conversation?: string;
}

interface ChatAreaProps {
    conversationId: string | null;
    conversationData?: { name: string; phone: string };
    messages: Message[];
    onSendMessage: (message: string) => void;
    isSending?: boolean;
    isAIActive: boolean; 
    onToggleAI: (mode: "AGENTE" | "OPERADOR") => void;
    isProfileOpen: boolean;
    onToggleProfile: () => void;
    onBack?: () => void; 
    onCloseConversation?: () => void;
    onOpenConversation?: () => void;
    isClosed?: boolean;
    
    // NOVO: Props para controle do histórico
    onLoadHistory?: () => void;
    isLoadingHistory?: boolean;
    hasMoreHistory?: boolean;
}

export function ChatArea({ 
    conversationData, 
    messages, 
    onSendMessage, 
    isSending, 
    isAIActive, 
    onToggleAI, 
    isProfileOpen, 
    onToggleProfile,
    onBack,
    onCloseConversation,
    onOpenConversation,
    isClosed,
    onLoadHistory,
    isLoadingHistory,
    hasMoreHistory = false
}: ChatAreaProps) {
    const [inputValue, setInputValue] = useState("");
    const messagesEndRef = useRef<HTMLDivElement>(null);

    // Ajuste: Só rola para baixo se não estiver carregando histórico antigo, 
    // para evitar que a tela pule pro final quando o usuário carregar mensagens velhas.
    useEffect(() => {
        if (!isLoadingHistory) {
            messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
        }
    }, [messages, isLoadingHistory]);

    const handleSend = () => {
        if (!inputValue.trim() || isClosed) return;
        onSendMessage(inputValue);
        setInputValue("");
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    };

    const formatMessageDate = (dateString: string) => {
        const date = new Date(dateString);
        if (isToday(date)) return "Hoje";
        if (isYesterday(date)) return "Ontem";
        if (differenceInDays(new Date(), date) < 7) return format(date, 'EEEE', { locale: ptBR });
        return format(date, "dd 'de' MMM", { locale: ptBR });
    };

    let lastDateLabel = "";

    return (
        <div className="flex flex-col h-full bg-background/50 relative">
            <div className="h-16 border-b border-border/50 px-4 flex items-center justify-between bg-card/50 backdrop-blur-xl shrink-0">
                <div className="flex items-center gap-2 sm:gap-3 min-w-0">
                    <Button variant="ghost" size="icon" onClick={onBack} className="md:hidden text-muted-foreground shrink-0">
                        <ArrowLeft className="w-5 h-5" />
                    </Button>
                    <Avatar className="w-9 h-9 sm:w-10 sm:h-10 border-2 border-primary/20 shrink-0">
                        <AvatarFallback className="bg-primary/10 text-primary font-medium">
                            {conversationData?.name?.charAt(0).toUpperCase() || "P"}
                        </AvatarFallback>
                    </Avatar>
                    <div className="min-w-0 truncate pr-2">
                        <h3 className="font-semibold text-foreground text-sm truncate">
                            {conversationData?.name || "Desconhecido"}
                        </h3>
                        <p className="text-xs text-muted-foreground truncate">{conversationData?.phone || "Sem telefone"}</p>
                    </div>
                </div>
                
                <div className="flex items-center gap-1.5 sm:gap-2 shrink-0">
                    {!isClosed && (
                        <Button 
                            variant="outline" 
                            size="sm" 
                            onClick={onCloseConversation} 
                            className="h-8 px-2 sm:px-3 text-xs text-muted-foreground border-border/50 hover:bg-destructive/10 hover:text-destructive hover:border-destructive/30 transition-colors"
                            title="Finalizar Atendimento"
                        >
                            <CheckCircle className="w-4 h-4 sm:mr-1.5" />
                            <span className="hidden sm:inline">Finalizar</span>
                        </Button>
                    )}

                    <button
                        onClick={() => onToggleAI(isAIActive ? "OPERADOR" : "AGENTE")}
                        className={cn(
                            "flex items-center gap-1.5 sm:gap-2 px-2 sm:px-4 py-1.5 rounded-full text-[10px] sm:text-xs font-bold transition-all border",
                            isAIActive 
                                ? "bg-purple-500/10 text-purple-500 border-purple-500/30 hover:bg-purple-500/20" 
                                : "bg-blue-500/10 text-blue-500 border-blue-500/30 hover:bg-blue-500/20"
                        )}
                    >
                        {isAIActive ? (
                            <><Sparkles className="w-3.5 h-3.5" /> <span className="hidden sm:inline">AGENTE IA ATIVO</span><span className="sm:hidden">IA</span></>
                        ) : (
                            <><User className="w-3.5 h-3.5" /> <span className="hidden sm:inline">OPERADOR MANUAL</span><span className="sm:hidden">HUMANO</span></>
                        )}
                    </button>

                    <Button variant="ghost" size="icon" onClick={onToggleProfile} className={cn("text-muted-foreground h-8 w-8 sm:h-9 sm:w-9", isProfileOpen && "bg-secondary")}>
                        <MoreVertical className="w-5 h-5" />
                    </Button>
                </div>
            </div>

            {isClosed && (
                <div className="bg-destructive/10 border-b border-destructive/20 p-2 flex items-center justify-center gap-2 text-destructive text-sm font-medium shrink-0">
                    <CheckCircle className="w-4 h-4" />
                    <span className="hidden sm:inline">Atendimento finalizado</span><span className="sm:hidden">Finalizado</span>
                    <Button variant="link" size="sm" onClick={onOpenConversation} className="text-destructive underline p-0 h-auto ml-2">
                        Reabrir
                    </Button>
                </div>
            )}

            <div className="flex-1 overflow-y-auto p-4 space-y-4 custom-scrollbar bg-dot-pattern">
                
                {/* NOVO: Botão de carregar histórico */}
                {hasMoreHistory && onLoadHistory && (
                    <div className="flex justify-center pb-2 pt-2">
                        <Button 
                            variant="ghost" 
                            size="sm" 
                            onClick={onLoadHistory}
                            disabled={isLoadingHistory}
                            className="text-[11px] uppercase tracking-wider font-bold text-muted-foreground bg-secondary/30 hover:bg-secondary/60 rounded-full px-5 h-8 transition-colors"
                        >
                            {isLoadingHistory ? (
                                <><Loader2 className="w-3.5 h-3.5 mr-2 animate-spin" /> Carregando...</>
                            ) : (
                                <><History className="w-3.5 h-3.5 mr-2" /> Carregar histórico de mensagens</>
                            )}
                        </Button>
                    </div>
                )}

                {messages.map((msg, idx) => {
                    const currentDateLabel = formatMessageDate(msg.created_at);
                    const showDateSeparator = currentDateLabel !== lastDateLabel;
                    lastDateLabel = currentDateLabel;
                    
                    const isIncoming = msg.direction === "INCOMING";

                    return (
                        <div key={msg.id} className="flex flex-col">
                            {showDateSeparator && (
                                <div className="flex justify-center my-4">
                                    <span className="text-[10px] uppercase font-bold text-muted-foreground bg-secondary/50 px-3 py-1 rounded-full">
                                        {currentDateLabel}
                                    </span>
                                </div>
                            )}
                            <div className={cn("flex w-full mb-2", isIncoming ? "justify-start" : "justify-end")}>
                                <div className={cn(
                                    "max-w-[85%] sm:max-w-[70%] rounded-2xl px-4 py-2 relative group shadow-sm",
                                    isIncoming 
                                        ? "bg-secondary text-foreground rounded-tl-none border border-border/50" 
                                        : msg.role === "assistant" 
                                            ? "bg-purple-600 text-white rounded-tr-none" 
                                            : "bg-primary text-primary-foreground rounded-tr-none"
                                )}>
                                    {!isIncoming && msg.role === "assistant" && (
                                        <div className="flex items-center gap-1 mb-1 opacity-70">
                                            <Sparkles className="w-3 h-3" />
                                            <span className="text-[10px] uppercase font-bold">Agente IA</span>
                                        </div>
                                    )}
                                    <p className="text-sm whitespace-pre-wrap break-words leading-relaxed">{msg.content}</p>
                                    <span className={cn(
                                        "text-[10px] mt-1.5 block font-medium opacity-60 text-right",
                                        isIncoming ? "text-muted-foreground" : "text-white/80"
                                    )}>
                                        {msg.time}
                                    </span>
                                </div>
                            </div>
                        </div>
                    );
                })}
                <div ref={messagesEndRef} className="h-1" />
            </div>

            <div className="p-3 sm:p-4 bg-background/50 border-t border-border/50 shrink-0">
                <div className="bg-card/50 border border-border/50 rounded-xl p-1 flex items-center gap-2 shadow-inner">
                    <Button variant="ghost" size="icon" className="text-muted-foreground hover:text-primary shrink-0"><Paperclip className="w-5 h-5" /></Button>
                    <Input
                        value={inputValue}
                        onChange={(e) => setInputValue(e.target.value)}
                        onKeyDown={handleKeyDown}
                        placeholder={isClosed ? "Atendimento fechado..." : "Escreva uma mensagem..."}
                        disabled={isClosed}
                        className="flex-1 bg-transparent border-none focus-visible:ring-0 shadow-none h-10 text-sm"
                    />
                    <Button 
                        onClick={handleSend} 
                        disabled={isSending || !inputValue.trim()} 
                        size="icon"
                        className="rounded-lg h-9 w-9 shrink-0"
                    >
                        {isSending ? <Loader2 className="w-5 h-5 animate-spin" /> : <Send className="w-5 h-5" />}
                    </Button>
                </div>
            </div>
        </div>
    );
}