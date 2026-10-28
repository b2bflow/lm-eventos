import { Send, Loader2, Paperclip, MoreVertical, Sparkles, CheckCircle, ArrowLeft, History, Phone, StickyNote, Zap, Smartphone } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useState, useRef, useEffect, useLayoutEffect } from "react";
import { cn } from "@/lib/utils";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { format, isToday, isYesterday, differenceInDays } from "date-fns";
import { ptBR } from "date-fns/locale";
import type { ChatMessage } from "@/lib/chatMessage";
import { parseSafeDate, formatSafeTime } from "@/lib/dateUtils";
import { MessageBody } from "./MessageBody";
import type { QuickReply } from "@/hooks/useLmSettings";

export type Message = ChatMessage;

interface ChatAreaProps {
    conversationId: string | null;
    conversationData?: { name: string; phone: string };
    messages: Message[];
    onSendMessage: (message: string) => void;
    onSendFile?: (file: File) => void;
    isSending?: boolean;
    isUploadingFile?: boolean;
    isAIActive: boolean;
    /** Muda para o modo pedido: AGENTE (retomar IA) ou OPERADOR (assumir). */
    onToggleAI: (mode: "AGENTE" | "OPERADOR") => void;
    /** Parceiro: a IA não atende, então "Retomar IA" fica desabilitado. */
    aiBlocked?: boolean;
    /** Ex.: "IA retomada por Erica" (quem fez a última passagem). */
    handoverInfo?: string;
    onAddNote?: (text: string) => void;
    onCall?: () => void;
    quickReplies?: QuickReply[];
    isProfileOpen: boolean;
    onToggleProfile: () => void;
    onBack?: () => void; 
    onCloseConversation?: () => void;
    onOpenConversation?: () => void;
    isClosed?: boolean;
    
    // Rolagem para cima: mensagens mais antigas da conversa (ou do histórico do cliente)
    onLoadOlder?: () => void;
    hasOlder?: boolean;
    isLoadingOlder?: boolean;
    // Ao chegar no início da conversa: carregar as conversas anteriores do cliente
    onLoadHistory?: () => void;
    hasMoreHistory?: boolean;
}

export function ChatArea({ 
    conversationData, 
    messages, 
    onSendMessage, 
    onSendFile,
    isSending, 
    isUploadingFile,
    isAIActive,
    onToggleAI,
    aiBlocked = false,
    handoverInfo,
    onAddNote,
    onCall,
    quickReplies = [],
    isProfileOpen, 
    onToggleProfile,
    onBack,
    onCloseConversation,
    onOpenConversation,
    isClosed,
    onLoadOlder,
    hasOlder = false,
    isLoadingOlder = false,
    onLoadHistory,
    hasMoreHistory = false
}: ChatAreaProps) {
    const [inputValue, setInputValue] = useState("");
    // Nota interna: só a equipe vê (não vai ao cliente nem à IA).
    const [noteMode, setNoteMode] = useState(false);
    const [quickOpen, setQuickOpen] = useState(false);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const scrollRef = useRef<HTMLDivElement>(null);
    const topSentinelRef = useRef<HTMLDivElement>(null);
    // Altura antes de carregar mensagens antigas: usada para manter a posição da rolagem.
    const heightBeforeOlder = useRef<number | null>(null);
    const nearBottom = useRef(true);
    const firstId = messages[0]?.id;
    const lastId = messages[messages.length - 1]?.id;
    const prevFirstId = useRef<string | undefined>(undefined);
    const prevLastId = useRef<string | undefined>(undefined);

    useLayoutEffect(() => {
        const el = scrollRef.current;
        if (!el) return;
        if (heightBeforeOlder.current !== null && firstId !== prevFirstId.current && prevFirstId.current !== undefined) {
            // Antigas entraram no topo: compensa a altura nova para o conteúdo não pular.
            el.scrollTop += el.scrollHeight - heightBeforeOlder.current;
            heightBeforeOlder.current = null;
        } else if (lastId !== prevLastId.current && (nearBottom.current || prevLastId.current === undefined)) {
            // Abertura da conversa ou mensagem nova com o usuário no fim: vai para a última.
            el.scrollTop = el.scrollHeight;
        }
        prevFirstId.current = firstId;
        prevLastId.current = lastId;
    }, [firstId, lastId]);

    useEffect(() => {
        const sentinel = topSentinelRef.current;
        const root = scrollRef.current;
        if (!sentinel || !root || !hasOlder || !onLoadOlder) return;
        const observer = new IntersectionObserver(
            (entries) => {
                if (entries[0]?.isIntersecting && !isLoadingOlder && prevLastId.current !== undefined) {
                    heightBeforeOlder.current = root.scrollHeight;
                    onLoadOlder();
                }
            },
            { root, rootMargin: "120px 0px 0px 0px" }
        );
        observer.observe(sentinel);
        return () => observer.disconnect();
    }, [hasOlder, isLoadingOlder, onLoadOlder, firstId]);

    // Imagem carregada depois da rolagem inicial muda a altura: mantém no fim se o usuário estava lá.
    const handleMediaLoaded = () => {
        const el = scrollRef.current;
        if (el && nearBottom.current && heightBeforeOlder.current === null) el.scrollTop = el.scrollHeight;
    };

    const handleScroll = () => {
        const el = scrollRef.current;
        if (!el) return;
        nearBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 160;
    };

    const handleSend = () => {
        if (!inputValue.trim()) return;
        if (noteMode) {
            onAddNote?.(inputValue.trim());
        } else {
            if (isClosed) return;
            onSendMessage(inputValue);
        }
        setInputValue("");
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    };

    const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
        const file = event.target.files?.[0];
        event.target.value = "";

        if (!file || isClosed || isUploadingFile) return;
        onSendFile?.(file);
    };

    const formatMessageDate = (dateString?: string | null) => {
        const date = parseSafeDate(dateString);
        if (!date) return "";

        try {
            if (isToday(date)) return "Hoje";
            if (isYesterday(date)) return "Ontem";
            if (Math.abs(differenceInDays(new Date(), date)) < 7) {
                return format(date, 'EEEE', { locale: ptBR });
            }
            return format(date, "dd 'de' MMM", { locale: ptBR });
        } catch {
            return "";
        }
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
                            <CheckCircle className="w-4 h-4 2xl:mr-1.5" />
                            <span className="hidden 2xl:inline">Finalizar</span>
                        </Button>
                    )}

                    {onCall && (
                        <Button variant="outline" size="sm" onClick={onCall} title="Ligar e registrar a ligação"
                            className="h-8 px-2 2xl:px-3 text-xs border-border/50">
                            <Phone className="w-4 h-4 2xl:mr-1.5" />
                            <span className="hidden 2xl:inline">Ligar</span>
                        </Button>
                    )}

                    {isAIActive ? (
                        <Button variant="outline" size="sm" onClick={() => onToggleAI("OPERADOR")}
                            title={handoverInfo ? `${handoverInfo}. Clique para assumir a conversa.` : "IA respondendo. Clique para assumir a conversa."}
                            className="h-8 px-2 sm:px-3 text-xs font-bold text-purple-600 border-purple-500/40 bg-purple-500/10 hover:bg-purple-500/20">
                            <Sparkles className="w-3.5 h-3.5 xl:mr-1.5" />
                            <span className="hidden xl:inline">IA ativa · Assumir</span>
                        </Button>
                    ) : (
                        <Button size="sm" onClick={() => onToggleAI("AGENTE")} disabled={aiBlocked}
                            title={aiBlocked ? "Parceiro fica com a Erica: a IA não atende este contato." : handoverInfo || "Devolver a conversa para a IA"}
                            className="h-8 px-2 sm:px-3 text-xs font-bold bg-purple-600 hover:bg-purple-700 text-white">
                            <Sparkles className="w-3.5 h-3.5 xl:mr-1.5" />
                            <span className="hidden xl:inline">Retomar IA</span>
                        </Button>
                    )}

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

            <div ref={scrollRef} onScroll={handleScroll} onLoadCapture={handleMediaLoaded} className="flex-1 overflow-y-auto p-4 space-y-4 custom-scrollbar bg-dot-pattern">

                {hasOlder && (
                    <div ref={topSentinelRef} className="flex justify-center py-2 text-muted-foreground">
                        {isLoadingOlder && <Loader2 className="w-4 h-4 animate-spin" />}
                    </div>
                )}

                {/* Início da conversa atual: oferece o histórico das conversas anteriores do cliente */}
                {!hasOlder && hasMoreHistory && onLoadHistory && (
                    <div className="flex justify-center pb-2 pt-2">
                        <Button 
                            variant="ghost" 
                            size="sm" 
                            onClick={() => {
                                heightBeforeOlder.current = scrollRef.current?.scrollHeight ?? null;
                                onLoadHistory();
                            }}
                            disabled={isLoadingOlder}
                            className="text-[11px] uppercase tracking-wider font-bold text-muted-foreground bg-secondary/30 hover:bg-secondary/60 rounded-full px-5 h-8 transition-colors"
                        >
                            {isLoadingOlder ? (
                                <><Loader2 className="w-3.5 h-3.5 mr-2 animate-spin" /> Carregando...</>
                            ) : (
                                <><History className="w-3.5 h-3.5 mr-2" /> Carregar histórico de mensagens</>
                            )}
                        </Button>
                    </div>
                )}

                {messages.map((msg) => {
                    const currentDateLabel = formatMessageDate(msg.created_at);
                    const showDateSeparator = !!currentDateLabel && currentDateLabel !== lastDateLabel;
                    if (currentDateLabel) {
                        lastDateLabel = currentDateLabel;
                    }
                    const displayTime = msg.time || formatSafeTime(msg.created_at);
                    
                    const isIncoming = msg.direction === "INCOMING";
                    const separator = showDateSeparator && (
                        <div className="flex justify-center my-4">
                            <span className="text-[10px] uppercase font-bold text-muted-foreground bg-secondary/50 px-3 py-1 rounded-full">
                                {currentDateLabel}
                            </span>
                        </div>
                    );

                    if (msg.direction === "INTERNAL") {
                        return (
                            <div key={msg.id} className="flex flex-col">
                                {separator}
                                {msg.message_type === "note" ? (
                                    <div className="flex justify-center mb-2">
                                        <div className="w-full sm:max-w-[75%] rounded-xl border border-amber-400/50 bg-amber-50 dark:bg-amber-500/10 px-3 py-2">
                                            <p className="flex items-center gap-1 text-[10px] font-bold uppercase tracking-wide text-amber-700 dark:text-amber-400">
                                                <StickyNote className="w-3 h-3" /> Nota interna{msg.author_name ? ` · ${msg.author_name}` : ""} · {msg.time}
                                            </p>
                                            <p className="text-sm text-foreground whitespace-pre-wrap break-words">{msg.content}</p>
                                        </div>
                                    </div>
                                ) : (
                                    <div className="flex justify-center mb-2">
                                        <span className="text-[11px] text-center text-muted-foreground bg-secondary/60 px-3 py-1 rounded-full max-w-full">
                                            {msg.content} · {msg.time}
                                        </span>
                                    </div>
                                )}
                            </div>
                        );
                    }

                    return (
                        <div key={msg.id} className="flex flex-col">
                            {separator}
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
                                    {!isIncoming && msg.sent_from_phone && (
                                        <div className="flex items-center gap-1 mb-1 opacity-70">
                                            <Smartphone className="w-3 h-3" />
                                            <span className="text-[10px] uppercase font-bold">Pelo WhatsApp</span>
                                        </div>
                                    )}
                                    <MessageBody message={msg} isIncoming={isIncoming} />
                                    <span className={cn(
                                        "text-[10px] mt-1.5 block font-medium opacity-60 text-right",
                                        isIncoming ? "text-muted-foreground" : "text-white/80"
                                    )}>
                                        {displayTime}
                                    </span>
                                </div>
                            </div>
                        </div>
                    );
                })}
                <div className="h-1" />
            </div>

            <div className="p-3 sm:p-4 bg-background/50 border-t border-border/50 shrink-0">
                {noteMode && (
                    <p className="text-[11px] text-amber-700 dark:text-amber-400 mb-1.5 flex items-center gap-1">
                        <StickyNote className="w-3 h-3" /> Nota interna: só a equipe vê. Não vai para o cliente nem para a IA.
                    </p>
                )}
                <div className={cn(
                    "border rounded-xl p-1 flex items-center gap-1 shadow-inner",
                    noteMode ? "bg-amber-50 dark:bg-amber-500/10 border-amber-400/60" : "bg-card/50 border-border/50"
                )}>
                    {onAddNote && (
                        <Button variant="ghost" size="icon" onClick={() => setNoteMode(!noteMode)}
                            title={noteMode ? "Voltar para mensagem ao cliente" : "Escrever nota interna"}
                            className={cn("shrink-0", noteMode ? "text-amber-600" : "text-muted-foreground hover:text-primary")}>
                            <StickyNote className="w-5 h-5" />
                        </Button>
                    )}
                    {onSendFile && !noteMode && (
                        <>
                            <input
                                ref={fileInputRef}
                                type="file"
                                className="hidden"
                                onChange={handleFileChange}
                                disabled={isClosed || isUploadingFile}
                            />
                            <Button
                                type="button"
                                variant="ghost"
                                size="icon"
                                onClick={() => fileInputRef.current?.click()}
                                disabled={isClosed || isUploadingFile}
                                className="text-muted-foreground hover:text-primary shrink-0"
                                title="Anexar arquivo"
                            >
                                {isUploadingFile ? <Loader2 className="w-5 h-5 animate-spin" /> : <Paperclip className="w-5 h-5" />}
                            </Button>
                        </>
                    )}
                    {quickReplies.length > 0 && !noteMode && (
                        <Popover open={quickOpen} onOpenChange={setQuickOpen}>
                            <PopoverTrigger asChild>
                                <Button variant="ghost" size="icon" title="Respostas rápidas" disabled={isClosed}
                                    className="text-muted-foreground hover:text-primary shrink-0">
                                    <Zap className="w-5 h-5" />
                                </Button>
                            </PopoverTrigger>
                            <PopoverContent align="start" side="top" className="w-[min(22rem,calc(100vw-2rem))] p-1 max-h-80 overflow-y-auto">
                                <p className="px-2 py-1.5 text-[10px] font-bold uppercase tracking-wide text-muted-foreground">Respostas rápidas</p>
                                {quickReplies.map((reply, index) => (
                                    <button key={`${reply.title}-${index}`}
                                        onClick={() => { setInputValue(reply.text); setQuickOpen(false); }}
                                        className="w-full text-left rounded-md px-2 py-1.5 hover:bg-secondary">
                                        <span className="block text-xs font-semibold">{reply.title}</span>
                                        <span className="block text-xs text-muted-foreground line-clamp-2">{reply.text}</span>
                                    </button>
                                ))}
                            </PopoverContent>
                        </Popover>
                    )}
                    <Input
                        value={inputValue}
                        onChange={(e) => setInputValue(e.target.value)}
                        onKeyDown={handleKeyDown}
                        placeholder={noteMode ? "Nota interna para a equipe..." : isClosed ? "Atendimento fechado..." : "Escreva uma mensagem..."}
                        disabled={isClosed && !noteMode}
                        className="flex-1 bg-transparent border-none focus-visible:ring-0 shadow-none h-10 text-sm"
                    />
                    <Button
                        onClick={handleSend}
                        disabled={(isSending && !noteMode) || !inputValue.trim()}
                        size="icon"
                        className={cn("rounded-lg h-9 w-9 shrink-0", noteMode && "bg-amber-500 hover:bg-amber-600")}
                        title={noteMode ? "Salvar nota" : "Enviar"}
                    >
                        {isSending && !noteMode ? <Loader2 className="w-5 h-5 animate-spin" /> : noteMode ? <StickyNote className="w-5 h-5" /> : <Send className="w-5 h-5" />}
                    </Button>
                </div>
            </div>
        </div>
    );
}
