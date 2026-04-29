import { useState, useEffect } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import api from "@/services/api";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import { LEAD_STATUS_LABELS, LEAD_STATUS_OPTIONS } from "@/constants/mappings";

interface LeadData {
  id: string | number;
  quote_id?: string;
  customer?: string;
  customer_id?: string;
  name?: string;
  phone?: string;
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
}

interface EditLeadDialogProps {
  lead: LeadData | null; 
  isOpen: boolean;
  onClose: () => void;
}

export function EditLeadDialog({ lead, isOpen, onClose }: EditLeadDialogProps) {
  const [formData, setFormData] = useState({
    name: "",
    phone: "",
    customer_state_now: "ANALYSIS",
    celebration_type: "",
    event_title: "",
    event_date: "",
    guest_count: 0,
    quoted_amount: "",
    contract_value: "",
    venue: "",
    notes: "",
    next_step: "",
  });
  
  const queryClient = useQueryClient();

  useEffect(() => {
    if (lead) {
      setFormData({
        name: lead.name || "",
        phone: lead.phone || "",
        customer_state_now: lead.customer_state_now || "ANALYSIS",
        celebration_type: lead.celebration_type || "",
        event_title: lead.event_title || "",
        event_date: lead.event_date ? lead.event_date.slice(0, 10) : "",
        guest_count: lead.guest_count || 0,
        quoted_amount: lead.quoted_amount ? String(lead.quoted_amount) : "",
        contract_value: lead.contract_value ? String(lead.contract_value) : "",
        venue: lead.venue || "",
        notes: lead.notes || "",
        next_step: lead.next_step || "",
      });
    }
  }, [lead]);

  const updateLeadMutation = useMutation({
    mutationFn: async () => {
      if (!lead) throw new Error("Sem lead selecionado");
      const endpoint = lead.quote_id ? `/crm/quotes/${lead.quote_id}/` : `/crm/customers/${lead.id}/`;
      const { data } = await api.patch(endpoint, {
        ...formData,
        event_date: formData.event_date || undefined,
        guest_count: Number(formData.guest_count || 0),
        quoted_amount: formData.quoted_amount ? parseFloat(formData.quoted_amount) : 0,
        contract_value: formData.contract_value ? parseFloat(formData.contract_value) : 0,
        proposal_sent_at: formData.quoted_amount ? new Date().toISOString() : undefined,
        last_interaction_at: formData.next_step || formData.notes ? new Date().toISOString() : undefined,
      });
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["leads"] });
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard-metrics"] });
      toast.success("Lead atualizado com sucesso.");
      onClose();
    },
    onError: (error: any) => {
      if (error.response?.data) {
        const errorData = error.response.data;
        const firstKey = Object.keys(errorData)[0];
        const errorMessage = errorData[firstKey];
        toast.error(`Erro em ${firstKey}: ${errorMessage}`);
      } else {
        toast.error("Erro ao atualizar as informações do Lead.");
      }
    }
  });

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="glass border-border/50 sm:max-w-[720px]">
        <DialogHeader>
          <DialogTitle>Editar Lead / Evento</DialogTitle>
        </DialogHeader>
        
        <div className="space-y-4 py-4 max-h-[70vh] overflow-y-auto pr-2">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Nome</Label>
              <Input 
                value={formData.name} 
                onChange={(e) => setFormData({...formData, name: e.target.value})} 
              />
            </div>

            <div className="space-y-2">
              <Label>Telefone</Label>
              <Input 
                value={formData.phone} 
                onChange={(e) => setFormData({...formData, phone: e.target.value})} 
              />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Tipo de Celebração</Label>
              <Input 
                value={formData.celebration_type} 
                onChange={(e) => setFormData({...formData, celebration_type: e.target.value})} 
              />
            </div>

            <div className="space-y-2">
              <Label>Nome do Evento</Label>
              <Input 
                value={formData.event_title} 
                onChange={(e) => setFormData({...formData, event_title: e.target.value})} 
              />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="space-y-2">
              <Label>Data do Evento</Label>
              <Input 
                type="date"
                value={formData.event_date} 
                onChange={(e) => setFormData({...formData, event_date: e.target.value})} 
              />
            </div>

            <div className="space-y-2">
              <Label>Convidados</Label>
              <Input 
                type="number"
                min="0"
                value={formData.guest_count} 
                onChange={(e) => setFormData({...formData, guest_count: Number(e.target.value)})} 
              />
            </div>

            <div className="space-y-2">
              <Label>Orçamento</Label>
              <Input 
                type="number"
                min="0"
                step="0.01"
                value={formData.quoted_amount} 
                onChange={(e) => setFormData({...formData, quoted_amount: e.target.value})} 
              />
            </div>

            <div className="space-y-2">
              <Label>Valor Fechado</Label>
              <Input 
                type="number"
                min="0"
                step="0.01"
                value={formData.contract_value} 
                onChange={(e) => setFormData({...formData, contract_value: e.target.value})} 
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label>Status do Funil</Label>
            <Select 
              value={formData.customer_state_now} 
              onValueChange={(val) => setFormData({...formData, customer_state_now: val})}
            >
              <SelectTrigger>
                <SelectValue placeholder="Selecione o status" />
              </SelectTrigger>
              <SelectContent className="glass border-border/50">
                {LEAD_STATUS_OPTIONS.map((status) => (
                  <SelectItem key={status} value={status}>
                    {LEAD_STATUS_LABELS[status]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label>Local</Label>
            <Input 
              value={formData.venue} 
              onChange={(e) => setFormData({...formData, venue: e.target.value})} 
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Próximo Passo</Label>
              <Input 
                value={formData.next_step} 
                onChange={(e) => setFormData({...formData, next_step: e.target.value})} 
              />
            </div>

            <div className="space-y-2">
              <Label>Notas da Negociação</Label>
              <Textarea 
                rows={4}
                value={formData.notes} 
                onChange={(e) => setFormData({...formData, notes: e.target.value})} 
              />
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancelar</Button>
          <Button 
            onClick={() => updateLeadMutation.mutate()} 
            className="bg-primary text-primary-foreground hover:bg-primary/90"
            disabled={updateLeadMutation.isPending}
          >
            {updateLeadMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Guardar Alterações
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
