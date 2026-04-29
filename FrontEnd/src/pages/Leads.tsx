import { toast } from "sonner";
import api from "@/services/api";
import { useState } from "react";
import { Filter, Search, TrendingUp, CalendarRange } from "lucide-react";
import { Lead } from "@/hooks/useLeads"; 
import { useLeads } from "@/hooks/useLeads";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Sidebar } from "@/components/layout/Sidebar";
import { LeadsTable } from "@/components/domain/crm/LeadsTable";
import { DateFilterProvider } from "@/contexts/DateFilterContext";
import { RegisterLead } from "@/components/features/leads/RegisterLead";
import { EditLeadDialog } from "@/components/domain/crm/EditLeadDialog";
import { LEAD_STATUS_LABELS, LEAD_STATUS_OPTIONS, LEAD_STATUS_STYLES } from "@/constants/mappings";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogClose } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";

const Leads = () => {
  const { 
    leads, isLoading, page, setPage, totalPages, refetch,
    statusFilter, setStatusFilter, searchTerm, setSearchTerm } = useLeads();
  const [selectedLead, setSelectedLead] = useState<Lead | null>(null);
  const [isEditOpen, setIsEditOpen] = useState(false);
  const [isDeleteOpen, setIsDeleteOpen] = useState(false);

  
  const handleDelete = async () => {
    if (!selectedLead) return;
    try {
      await api.delete(`/crm/quotes/${selectedLead.id}/`);
      toast.success("Cotação excluída com sucesso");
      setIsDeleteOpen(false);
      refetch(); 
    } catch (error) {
      toast.error("Erro ao excluir o Lead.");
      console.error(error);
    }
  };

  const projectedRevenue = leads.reduce((sum, lead) => sum + (lead.contract_value || lead.quoted_amount || 0), 0);
  const eventsScheduled = leads.filter((lead) => lead.event_date).length;

  return (
    <DateFilterProvider>
      <div className="flex h-screen w-full bg-background overflow-hidden">
        <Sidebar />
        <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
          <main className="flex-1 p-6 overflow-y-auto">
            <div className="max-w-7xl mx-auto space-y-6">
              
              <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
                <div>
                  <h1 className="text-2xl font-bold">Pipeline de Eventos</h1>
                  <p className="text-muted-foreground">Gerencie leads, eventos, negociações e fechamento comercial.</p>
                </div>
                <RegisterLead />
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="glass rounded-xl p-4">
                  <div className="text-xs uppercase tracking-wider text-muted-foreground">Leads na página</div>
                  <div className="mt-2 text-3xl font-bold">{leads.length}</div>
                </div>
                <div className="glass rounded-xl p-4">
                  <div className="text-xs uppercase tracking-wider text-muted-foreground">Receita projetada visível</div>
                  <div className="mt-2 text-3xl font-bold">
                    {new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(projectedRevenue)}
                  </div>
                </div>
                <div className="glass rounded-xl p-4">
                  <div className="text-xs uppercase tracking-wider text-muted-foreground">Eventos agendados</div>
                  <div className="mt-2 text-3xl font-bold">{eventsScheduled}</div>
                </div>
              </div>

              <div className="glass rounded-xl p-4 space-y-4">
                <div className="flex flex-col lg:flex-row gap-4 lg:items-center lg:justify-between">
                  <div className="flex items-center gap-2">
                    <Filter className="w-4 h-4 text-muted-foreground" />
                    <span className="text-sm font-medium">Filtros do funil</span>
                  </div>

                  <div className="relative w-full lg:max-w-sm">
                    <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                    <Input
                      value={searchTerm}
                      onChange={(e) => {
                        setSearchTerm(e.target.value);
                        setPage(1);
                      }}
                      placeholder="Buscar por nome, telefone ou tipo de evento"
                      className="pl-9 bg-background/60"
                    />
                  </div>
                </div>

                <div className="flex flex-wrap gap-2">
                  <Button
                    variant={statusFilter === "all" ? "default" : "outline"}
                    size="sm"
                    onClick={() => {
                      setStatusFilter("all");
                      setPage(1);
                    }}
                  >
                    Todas as Tags
                  </Button>
                  {LEAD_STATUS_OPTIONS.map((status) => (
                    <button
                      key={status}
                      onClick={() => {
                        setStatusFilter(status);
                        setPage(1);
                      }}
                      className={`inline-flex items-center rounded-full border px-3 py-1.5 text-xs font-semibold transition-all ${
                        statusFilter === status ? "scale-[1.02] shadow-sm" : "opacity-80 hover:opacity-100"
                      } ${LEAD_STATUS_STYLES[status]}`}
                    >
                      {LEAD_STATUS_LABELS[status]}
                    </button>
                  ))}
                </div>

                <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
                  <Badge variant="outline" className="gap-1">
                    <TrendingUp className="w-3 h-3" />
                    Venda e Perdido são definidos manualmente
                  </Badge>
                  <Badge variant="outline" className="gap-1">
                    <CalendarRange className="w-3 h-3" />
                    Análise, Orçamento e Negociando atualizam automaticamente
                  </Badge>
                </div>
              </div>

              <LeadsTable 
                data={leads} 
                isLoading={isLoading} 
                onEdit={(lead) => { 
                  setSelectedLead(lead); 
                  setIsEditOpen(true); 
                }} 
                onDelete={(lead) => {
                  setSelectedLead(lead);
                  setIsDeleteOpen(true);
                }}
              />

              <div className="flex items-center justify-between px-2">
                <span className="text-sm text-muted-foreground">Página {page} de {totalPages}</span>
                <div className="flex gap-2">
                  <Button variant="outline" size="sm" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}>Anterior</Button>
                  <Button variant="outline" size="sm" onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages}>Próximo</Button>
                </div>
              </div>

            </div>
          </main>
          
          <EditLeadDialog lead={selectedLead} isOpen={isEditOpen} onClose={() => setIsEditOpen(false)} />
          
              <Dialog open={isDeleteOpen} onOpenChange={setIsDeleteOpen}>
            <DialogContent className="glass border-border/50">
              <DialogHeader><DialogTitle>Confirmar Exclusão</DialogTitle></DialogHeader>
              <p className="text-muted-foreground py-4">Tem a certeza que deseja excluir esta cotação de <strong>{selectedLead?.name}</strong>?</p>
              <DialogFooter>
                <DialogClose asChild><Button variant="outline">Cancelar</Button></DialogClose>
                <Button onClick={handleDelete} variant="destructive">Excluir Cotação</Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </div>
    </DateFilterProvider>
  );
};

export default Leads;
