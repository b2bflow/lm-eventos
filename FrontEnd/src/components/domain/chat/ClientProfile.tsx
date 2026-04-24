import { Phone, Tag, Edit, User, CheckCircle, ArrowLeft, History } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";

interface PastConversation {
  id: string;
  created_at: string;
  status: string;
  final_customer_status?: string;
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
  } | undefined;
  onEdit: () => void; 
  onCloseMobile?: () => void; 
  onCloseConversation?: () => void; 
  isClosed?: boolean; 
  onSelectConversation?: (id: string) => void; // NOVO: Redirecionamento
}

const getStatusDisplay = (status: string | undefined) => {
  switch(status) {
    case 'ANALYSIS': return { label: 'Análise', color: 'text-slate-600 bg-slate-500/10 border-slate-500/20' };
    case 'BUDGET': return { label: 'Orçamento', color: 'text-amber-600 bg-amber-500/10 border-amber-500/20' };
    case 'NEGOTIATING': return { label: 'Negociando', color: 'text-sky-600 bg-sky-500/10 border-sky-500/20' };
    case 'WON': return { label: 'Venda', color: 'text-emerald-600 bg-emerald-500/10 border-emerald-500/20' };
    case 'LOST': return { label: 'Perdido', color: 'text-rose-600 bg-rose-500/10 border-rose-500/20' };
    default: return { label: 'Análise', color: 'text-slate-600 bg-slate-500/10 border-slate-500/20' };
  }
};

export function ClientProfile({ customer, onEdit, onCloseMobile, onCloseConversation, isClosed, onSelectConversation }: ClientProfileProps) {
  
  if (!customer) return null;

  // Se a conversa já foi fechada, exibe o status "congelado" dela, caso contrário, o atual do banco.
  const displayStatus = isClosed && customer.final_customer_status ? customer.final_customer_status : customer.customer_status;
  const statusInfo = getStatusDisplay(displayStatus);

  return (
    <div className="flex flex-col h-full bg-card/30">
      <div className="p-4 border-b border-border/50 bg-background/50 flex items-center justify-between shrink-0">
        <h2 className="text-sm font-bold text-foreground uppercase tracking-wider">Perfil do Cliente</h2>
        <div className="flex items-center gap-2">
            <Button variant="ghost" size="icon" onClick={onEdit} className="h-8 w-8 text-muted-foreground hover:text-primary">
              <Edit className="w-4 h-4" />
            </Button>
            {onCloseMobile && (
               <Button variant="ghost" size="icon" onClick={onCloseMobile} className="md:hidden h-8 w-8 text-muted-foreground hover:text-primary">
                 <ArrowLeft className="w-5 h-5" />
               </Button>
            )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto scrollbar-thin p-6 space-y-6">
        <div className="flex flex-col items-center text-center">
          <Avatar className="w-24 h-24 border-2 border-primary/20 mb-4 shadow-xl">
            <AvatarFallback className="bg-secondary text-secondary-foreground text-2xl font-bold">
              {customer.customer_name.substring(0, 2).toUpperCase()}
            </AvatarFallback>
          </Avatar>
          <h2 className="text-xl font-bold text-foreground mb-1">{customer.customer_name}</h2>
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
                          {new Date(conv.created_at).toLocaleDateString()}
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
                          #{conv.id.slice(-6)}
                        </span>
                        <span className={cn("text-[9px] font-bold", pastStatusInfo.color.split(" ")[0])}>
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
    </div>
  );
}
