import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import api from '@/services/api';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger,
  DialogFooter
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Loader2, Plus, Save } from 'lucide-react';
import { toast } from 'sonner';

const leadSchema = z.object({
  name: z.string().min(3, "Mínimo 3 caracteres"),
  phone: z.string().min(8, "Telefone inválido"),
  celebration_type: z.string().min(3, "Informe o tipo de celebração"),
  event_title: z.string().optional(),
  event_date: z.string().optional(),
  guest_count: z.coerce.number().min(0).optional(),
  quoted_amount: z.string().optional(),
  venue: z.string().optional(),
  notes: z.string().optional(),
});

type LeadFormValues = z.infer<typeof leadSchema>;

export function RegisterLead() {
  const [isOpen, setIsOpen] = useState(false);
  const queryClient = useQueryClient();

  const form = useForm<LeadFormValues>({
    resolver: zodResolver(leadSchema),
    defaultValues: {
      name: '',
      phone: '',
      celebration_type: '',
      event_title: '',
      event_date: '',
      guest_count: 0,
      quoted_amount: '',
      venue: '',
      notes: '',
    }
  });

  const { isSubmitting } = form.formState;

  const mutation = useMutation({
    mutationFn: async (data: LeadFormValues) => {
      const leadResponse = await api.post('/crm/customers/', {
        name: data.name,
        phone: data.phone,
        celebration_type: data.celebration_type,
        event_title: data.event_title || data.celebration_type,
        event_date: data.event_date || undefined,
        guest_count: data.guest_count || 0,
        quoted_amount: data.quoted_amount ? parseFloat(data.quoted_amount) : 0,
        venue: data.venue || undefined,
        notes: data.notes || undefined,
      });
      return leadResponse.data;
    },
    onSuccess: () => {
      toast.success("Lead cadastrado com sucesso na etapa Análise.");
      queryClient.invalidateQueries({ queryKey: ['leads'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard-metrics'] });

      setIsOpen(false);
      form.reset();
    },
    onError: (error: any) => {
      console.error(error);
      const msg = error.response?.data?.detail || "Erro ao criar lead.";
      toast.error(msg);
    }
  });

  const onSubmit = (data: LeadFormValues) => mutation.mutate(data);

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DialogTrigger asChild>
        <Button className="gradient-primary text-primary-foreground shadow-lg shadow-primary/20 hover:shadow-primary/30 transition-all duration-300">
          <Plus className="w-4 h-4 mr-2" /> Novo Lead
        </Button>
      </DialogTrigger>
      
      <DialogContent className="glass border-border/50 max-w-2xl">
        <DialogHeader>
          <DialogTitle>Novo Lead / Evento</DialogTitle>
        </DialogHeader>

        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6 py-4">
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Nome Completo</Label>
              <Input placeholder="Ex: João Silva" {...form.register('name')} />
              {form.formState.errors.name && <span className="text-red-500 text-xs">{form.formState.errors.name.message}</span>}
            </div>

            <div className="space-y-2">
              <Label>Telefone (WhatsApp)</Label>
              <Input placeholder="5511999999999" {...form.register('phone')} />
              {form.formState.errors.phone && <span className="text-red-500 text-xs">{form.formState.errors.phone.message}</span>}
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Tipo de Celebração</Label>
              <Input placeholder="Ex: Casamento, Formatura, Corporativo" {...form.register('celebration_type')} />
              {form.formState.errors.celebration_type && <span className="text-red-500 text-xs">{form.formState.errors.celebration_type.message}</span>}
            </div>

            <div className="space-y-2">
              <Label>Nome do Evento</Label>
              <Input placeholder="Ex: Casamento Ana e Caio" {...form.register('event_title')} />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="space-y-2">
              <Label>Data do Evento</Label>
              <Input type="date" {...form.register('event_date')} />
            </div>

            <div className="space-y-2">
              <Label>Número de Convidados</Label>
              <Input type="number" min="0" {...form.register('guest_count')} />
            </div>

            <div className="space-y-2">
              <Label>Receita Projetada</Label>
              <Input type="number" min="0" step="0.01" placeholder="0,00" {...form.register('quoted_amount')} />
            </div>
          </div>

          <div className="space-y-2">
            <Label>Local / Espaço</Label>
            <Input placeholder="Ex: Espaço Jardim Imperial" {...form.register('venue')} />
          </div>

          <div className="space-y-2">
            <Label>Contexto Comercial</Label>
            <Textarea
              rows={4}
              placeholder="Anote briefing, preferências, urgência e próximos passos."
              {...form.register('notes')}
            />
            <p className="text-xs text-muted-foreground">
              A tag inicial será <strong>Análise</strong>. Ao registrar orçamento ou interação posterior, o backend atualiza o funil automaticamente.
            </p>
          </div>

          <DialogFooter>
             <Button type="button" variant="outline" onClick={() => setIsOpen(false)}>Cancelar</Button>
             <Button type="submit" disabled={isSubmitting} className="gradient-primary">
               {isSubmitting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : (
                 <div className="flex items-center gap-2">
                    <Save className="w-4 h-4" /> Salvar Lead
                 </div>
               )}
             </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
