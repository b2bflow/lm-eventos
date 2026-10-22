import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Phone, Tag, Edit, User, CheckCircle, History, SquareKanban, Contact, UserCheck } from "lucide-react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Separator } from "@/components/ui/separator";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import { formatSafeDate } from "@/lib/dateUtils";
import { LEAD_STATUS_LABELS, LEAD_STATUS_STYLES, OWNER_LABELS, PRODUCT_LABELS, resolveStage } from "@/constants/mappings";
import { NewLeadDialog } from "@/components/domain/funnel/NewLeadDialog";

const NO_ASSIGNEE = "__none__";
const AI_ASSIGNEE = "__ia__";

interface PastConversation {
  id: string;
  created_at: string;
  status: string;
  final_customer_status?: string;
}

interface PastQuote {
  id: string;
  created_at: string;
  status?: string;
  customer_state_now?: string;
  event_title?: string | null;
  quoted_amount?: number;
  contract_value?: number;
}

interface ClientProfileProps {
  customer: {
    id: string; 
    conversation_id?: string;
    customer_name: string;
    customer_phone: string;
    tag?: string;
    customer_status?: string; 
    final_customer_status?: string;
    past_conversations?: PastConversation[];
    past_quotes?: PastQuote[];
    assignee?: string | null;
    customer_product?: string | null;
    customer_human_operator?: boolean;
    customer_funnel_entered_at?: string | null;
  } | undefined;
  open: boolean;
  onClose: () => void;
  onEdit: () => void;
  onCloseConversation?: () => void;
  isClosed?: boolean; 
  onSelectConversation?: (id: string) => void; // NOVO: Redirecionamento
  onAssign?: (assignee: string | null) => void;
  onCall?: () => void;
}

const getStatusDisplay = (status: string | undefined) => {
  const stage = resolveStage(status);
  return { label: LEAD_STATUS_LABELS[stage], color: LEAD_STATUS_STYLES[stage] };
};

/** Perfil do cliente da conversa aberta, em popup centralizado. */
export function ClientProfile({ customer, open, onClose, onEdit, onCloseConversation, isClosed, onSelectConversation, onAssign, onCall }: ClientProfileProps) {
  const navigate = useNavigate();
  const [converting, setConverting] = useState(false);

  if (!customer) return null;
  const inFunnel = !!customer.customer_funnel_entered_at;
  // Com a IA atendendo, a responsável pela conversa é a IA; quem assume escolhe o responsável.
  const aiActive = customer.tag === "AGENTE";

  // Se a conversa já foi fechada, exibe o status "congelado" dela, caso contrário, o atual do banco.
  const displayStatus = isClosed && customer.final_customer_status ? customer.final_customer_status : customer.customer_status;
  const statusInfo = getStatusDisplay(displayStatus);

  return (
    <>
      <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
        <DialogContent className="sm:max-w-lg p-0 sm:p-0 gap-0 flex flex-col overflow-hidden sm:max-h-[85vh] bg-card">
          <div className="p-4 pr-12 border-b border-border/50 bg-background/50 flex items-center justify-between shrink-0">
            <DialogTitle className="text-sm font-bold text-foreground uppercase tracking-wider">Perfil do Cliente</DialogTitle>
            <DialogDescription className="sr-only">Dados do contato, responsável e histórico da conversa.</DialogDescription>
            <Button variant="ghost" size="icon" onClick={onEdit} title="Editar lead" className="h-8 w-8 text-muted-foreground hover:text-primary">
              <Edit className="w-4 h-4" />
            </Button>
          </div>

          <div className="flex-1 overflow-y-auto scrollbar-thin p-6 space-y-6">
            <div className="flex flex-col items-center text-center">
              <Avatar className="w-24 h-24 border-2 border-primary/20 mb-4 shadow-xl">
                <AvatarFallback className="bg-secondary text-secondary-foreground text-2xl font-bold">
                  {(customer.customer_name || "Desconhecido").substring(0, 2).toUpperCase()}
                </AvatarFallback>
              </Avatar>
              <h2 className="text-xl font-bold text-foreground mb-1">{customer.customer_name || "Desconhecido"}</h2>
            </div>

            <div className="grid grid-cols-2 gap-2">
              {inFunnel ? (
                <Button size="sm" variant="outline" onClick={() => navigate(`/funil?lead=${customer.id}`)}
                  disabled={customer.customer_human_operator} title={customer.customer_human_operator ? "Parceiro não entra no funil" : "Abrir o card do lead"}>
                  <SquareKanban className="w-4 h-4 mr-1" /> Card no funil
                </Button>
              ) : (
                <Button size="sm" variant="outline" onClick={() => setConverting(true)}
                  disabled={customer.customer_human_operator} title={customer.customer_human_operator ? "Parceiro não entra no funil" : "Abrir um lead no funil para este contato"}>
                  <SquareKanban className="w-4 h-4 mr-1" /> Converter em lead
                </Button>
              )}
              <Button size="sm" variant="outline" onClick={() => navigate(`/contatos?contato=${customer.id}`)}>
                <Contact className="w-4 h-4 mr-1" /> Contato
              </Button>
            </div>

            <Separator className="bg-border/50" />

            <div className="space-y-3">
              <h3 className="text-xs font-bold text-muted-foreground uppercase tracking-wider flex items-center gap-2">
                <UserCheck className="w-4 h-4" /> Responsável pela conversa
              </h3>
              <Select value={aiActive ? AI_ASSIGNEE : customer.assignee || NO_ASSIGNEE}
                onValueChange={(v) => onAssign?.(v === NO_ASSIGNEE ? null : v)} disabled={!onAssign || aiActive}>
                <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {aiActive && <SelectItem value={AI_ASSIGNEE}>IA</SelectItem>}
                  <SelectItem value={NO_ASSIGNEE}>Sem responsável</SelectItem>
                  {Object.entries(OWNER_LABELS).map(([key, label]) => <SelectItem key={key} value={key}>{label}</SelectItem>)}
                </SelectContent>
              </Select>
              {aiActive && (
                <p className="text-xs text-muted-foreground">A IA está atendendo. Assuma a conversa para passá-la a alguém da equipe.</p>
              )}
              {customer.customer_human_operator && (
                <p className="text-xs text-rose-600">Parceiro ou cliente antigo: fica com a Erica e a IA não atende.</p>
              )}
            </div>

            <Separator className="bg-border/50" />

            <div className="space-y-4">
              <h3 className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Contato</h3>
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-secondary/50 flex items-center justify-center shrink-0">
                  <Phone className="w-4 h-4 text-muted-foreground" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-xs text-muted-foreground">WhatsApp</p>
                  <p className="text-sm font-medium text-foreground truncate">{customer.customer_phone || "Sem número"}</p>
                </div>
                {onCall && customer.customer_phone && (
                  <Button size="sm" variant="outline" onClick={onCall} className="shrink-0">
                    <Phone className="w-4 h-4 mr-1" /> Ligar
                  </Button>
                )}
              </div>
            </div>

            <Separator className="bg-border/50" />

            <div className="space-y-4">
              <h3 className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Status Comercial</h3>
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-secondary/50 flex items-center justify-center shrink-0">
                  <User className="w-4 h-4 text-muted-foreground" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-xs text-muted-foreground mb-1">
                    {isClosed ? "Status ao fechar a conversa" : "Status Atual"}
                  </p>
                  <span className={cn("px-2.5 py-1 rounded-md text-[10px] font-bold border", statusInfo.color)}>
                    {statusInfo.label}
                  </span>
                  {customer.customer_product && (
                    <span className="ml-1.5 px-2.5 py-1 rounded-md text-[10px] font-bold border border-border/60 text-muted-foreground">
                      {PRODUCT_LABELS[customer.customer_product] || customer.customer_product}
                    </span>
                  )}
                </div>
              </div>
              
              <div className="flex items-center gap-3 mt-2">
                <div className="w-8 h-8 rounded-lg bg-secondary/50 flex items-center justify-center shrink-0">
                  <Tag className="w-4 h-4 text-muted-foreground" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-xs text-muted-foreground">ID do Cliente</p>
                  <p className="text-xs font-mono text-muted-foreground truncate">{customer.id}</p>
                </div>
              </div>
            </div>

            {/* NOVO: Bloco de Histórico de Conversas (Clicável) */}
            {customer.past_conversations && customer.past_conversations.length > 0 && (
              <>
                <Separator className="bg-border/50" />
                <div className="space-y-3">
                  <h3 className="text-xs font-bold text-muted-foreground uppercase tracking-wider flex items-center gap-2">
                    <History className="w-4 h-4" /> Histórico Comercial
                  </h3>
                  <div className="space-y-2">
                    {customer.past_conversations.map(conv => {
                      const pastStatusInfo = getStatusDisplay(conv.final_customer_status);
                      return (
                        <div 
                          key={conv.id} 
                          onClick={() => onSelectConversation?.(conv.id)}
                          className="p-2.5 rounded-lg bg-secondary/30 hover:bg-secondary/60 cursor-pointer border border-border/50 transition-all hover:scale-[1.02]"
                        >
                          <div className="flex justify-between items-center mb-1.5">
                            <span className="text-[11px] font-bold text-foreground">
                              {formatSafeDate(conv.created_at, "dd/MM/yyyy")}
                            </span>
                            <span className={cn(
                              "text-[9px] font-bold px-1.5 py-0.5 rounded",
                              conv.status === 'CLOSED' ? "bg-muted text-muted-foreground" : "bg-primary/20 text-primary"
                            )}>
                              {conv.status === 'CLOSED' ? 'Finalizado' : 'Aberto'}
                            </span>
                          </div>
                          <div className="flex justify-between items-center">
                            <span className="text-[10px] text-muted-foreground font-mono">
                              #{String(conv.id || "").slice(-6)}
                            </span>
                            <span className={cn("text-[9px] font-bold", (pastStatusInfo.color || "").split(" ")[0])}>
                              {pastStatusInfo.label}
                            </span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </>
            )}

            {customer.past_quotes && customer.past_quotes.length > 0 && (
              <>
                <Separator className="bg-border/50" />
                <div className="space-y-3">
                  <h3 className="text-xs font-bold text-muted-foreground uppercase tracking-wider flex items-center gap-2">
                    <History className="w-4 h-4" /> Cotações anteriores
                  </h3>
                  <div className="space-y-2">
                    {customer.past_quotes.map((quote) => {
                      const quoteStatus = quote.status || quote.customer_state_now;
                      const quoteStatusInfo = getStatusDisplay(quoteStatus);
                      const amount = quote.contract_value || quote.quoted_amount || 0;
                      return (
                        <div key={quote.id} className="p-2.5 rounded-lg bg-secondary/30 border border-border/50">
                          <div className="flex justify-between gap-2 mb-1.5">
                            <span className="text-[11px] font-bold text-foreground truncate">
                              {quote.event_title || "Cotação sem título"}
                            </span>
                            <span className={cn("text-[9px] font-bold", (quoteStatusInfo.color || "").split(" ")[0])}>
                              {quoteStatusInfo.label}
                            </span>
                          </div>
                          <div className="flex justify-between items-center text-[10px] text-muted-foreground">
                            <span>{formatSafeDate(quote.created_at, "dd/MM/yyyy")}</span>
                            <span>
                              {new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(amount)}
                            </span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </>
            )}

            {/* NOVO: Botão de Finalizar Atendimento na base */}
            {!isClosed && onCloseConversation && (
              <>
                <Separator className="bg-border/50" />
                <div className="pt-2 pb-6">
                  <Button 
                    variant="outline" 
                    className="w-full text-destructive border-destructive/20 hover:bg-destructive/10 hover:text-destructive transition-colors"
                    onClick={onCloseConversation}
                  >
                    <CheckCircle className="w-4 h-4 mr-2" />
                    Finalizar Atendimento
                  </Button>
                </div>
              </>
            )}

          </div>
        </DialogContent>
      </Dialog>
      <NewLeadDialog open={converting} onClose={() => setConverting(false)}
        contact={{ id: customer.id, name: customer.customer_name, phone: customer.customer_phone }} />
    </>
  );
}
