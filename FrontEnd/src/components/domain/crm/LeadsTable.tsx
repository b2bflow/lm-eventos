import { 
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow 
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { 
  Pencil, Trash2, Phone, CalendarDays, Loader2, PartyPopper, Users, Wallet
} from "lucide-react";
import { 
  LEAD_STATUS_LABELS, 
  LEAD_STATUS_STYLES
} from "@/constants/mappings";

interface Lead {
  id: string;
  name: string;
  phone: string;
  customer_state_now: string;
  customer_custom_tag?: string | null;
  celebration_type?: string | null;
  event_title?: string | null;
  event_date?: string | null;
  guest_count?: number;
  quoted_amount?: number;
  contract_value?: number;
  created_at: string;
  updated_at: string;
}

interface LeadsTableProps {
  data: Lead[];
  isLoading: boolean;
  onEdit: (lead: Lead) => void;
  onDelete: (lead: Lead) => void;
}

export function LeadsTable({ data, isLoading, onEdit, onDelete }: LeadsTableProps) {
  if (isLoading) {
    return (
        <div className="h-64 flex flex-col items-center justify-center text-muted-foreground bg-card/50 rounded-xl border border-border/50">
        <Loader2 className="w-8 h-8 animate-spin mb-2 text-primary" />
        <p>Carregando leads e eventos...</p>
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <div className="h-64 flex items-center justify-center text-muted-foreground bg-card/50 rounded-xl border border-border/50">
        Nenhum lead encontrado.
      </div>
    );
  }

  return (
    <div className="glass rounded-xl overflow-hidden border border-border/50">
      <Table>
        <TableHeader className="bg-secondary/30">
          <TableRow className="hover:bg-transparent border-border/50">
            <TableHead>Cliente</TableHead>
            <TableHead>Evento</TableHead>
            <TableHead>Contato</TableHead>
            <TableHead>Tag</TableHead>
            <TableHead>Projeção</TableHead>
            <TableHead className="text-right">Ações</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.map((lead) => (
            <TableRow key={lead.id} className="hover:bg-secondary/20 border-border/50 transition-colors">
              <TableCell>
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-lg bg-secondary/50 flex items-center justify-center text-muted-foreground">
                    <PartyPopper className="w-4 h-4" />
                  </div>
                  <div>
                    <p className="font-medium text-foreground">{lead.name || "Lead sem nome"}</p>
                    <p className="text-xs text-muted-foreground">{lead.celebration_type || "Tipo de celebração não definido"}</p>
                  </div>
                </div>
              </TableCell>
              <TableCell>
                <div className="flex flex-col gap-1 text-sm">
                  <span className="font-medium text-foreground">{lead.event_title || "Evento em qualificação"}</span>
                  <div className="flex items-center gap-3 text-xs text-muted-foreground">
                    <span className="flex items-center gap-1">
                      <CalendarDays className="w-3.5 h-3.5" />
                      {lead.event_date ? new Date(lead.event_date).toLocaleDateString() : "Sem data"}
                    </span>
                    <span className="flex items-center gap-1">
                      <Users className="w-3.5 h-3.5" />
                      {lead.guest_count || 0} convidados
                    </span>
                  </div>
                </div>
              </TableCell>
              <TableCell>
                <div className="flex flex-col gap-1">
                  <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <Phone className="w-3 h-3" /> {lead.phone}
                  </div>
                </div>
              </TableCell>
              <TableCell>
                <Badge 
                  variant="outline"
                  className={LEAD_STATUS_STYLES[lead.customer_state_now] || "bg-secondary"}
                >
                  {LEAD_STATUS_LABELS[lead.customer_state_now] || lead.customer_state_now}
                </Badge>
              </TableCell>
              <TableCell className="text-muted-foreground text-sm">
                <div className="flex flex-col gap-1">
                  <div className="flex items-center gap-2">
                    <Wallet className="w-3.5 h-3.5" />
                    {new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(
                      lead.contract_value || lead.quoted_amount || 0
                    )}
                  </div>
                  <span className="text-xs">Atualizado em {new Date(lead.updated_at).toLocaleDateString()}</span>
                </div>
              </TableCell>
              <TableCell className="text-right">
                <div className="flex justify-end gap-2">
                  <Button 
                    variant="ghost" 
                    size="icon" 
                    className="h-8 w-8 hover:text-primary hover:bg-primary/10"
                    onClick={() => onEdit(lead)}
                  >
                    <Pencil className="w-4 h-4" />
                  </Button>
                  <Button 
                    variant="ghost" 
                    size="icon" 
                    className="h-8 w-8 hover:text-destructive hover:bg-destructive/10"
                    onClick={() => onDelete(lead)}
                  >
                    <Trash2 className="w-4 h-4" />
                  </Button>
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
