import { BadgeCheck, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { LEAD_STATUS_LABELS, LEAD_STATUS_STYLES, OWNER_LABELS, PRODUCT_LABELS } from "@/constants/mappings";
import { formatBRL, formatDateTime, formatDay, phoneDisplay } from "@/lib/format";
import { useFunnelList, type FunnelFilters } from "@/hooks/useFunnel";

/** Funil em lista: os mesmos leads e filtros do quadro, numa tabela só (mais recentes primeiro). */
export function FunnelListView({ filters, onOpen }: { filters: FunnelFilters; onOpen: (id: string) => void }) {
  const { data, isLoading, fetchNextPage, hasNextPage, isFetchingNextPage } = useFunnelList(filters, true);
  const leads = data?.pages.flatMap((p) => p.results) ?? [];
  const total = data?.pages[0]?.count ?? 0;

  if (isLoading) {
    return <div className="flex justify-center py-20"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>;
  }

  return (
    <div className="glass rounded-2xl border border-border/50 overflow-hidden">
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Nome</TableHead>
              <TableHead>Telefone</TableHead>
              <TableHead>Produto</TableHead>
              <TableHead>Etapa</TableHead>
              <TableHead>Responsável</TableHead>
              <TableHead>Data do evento</TableHead>
              <TableHead className="text-right">Valor</TableHead>
              <TableHead>Última interação</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {leads.length === 0 && (
              <TableRow>
                <TableCell colSpan={8} className="py-10 text-center text-sm text-muted-foreground">Nenhum lead encontrado.</TableCell>
              </TableRow>
            )}
            {leads.map((lead) => {
              const value = lead.contract_value || lead.quoted_amount || 0;
              return (
                <TableRow key={lead.id} className="cursor-pointer" onClick={() => onOpen(lead.id)}>
                  <TableCell className="font-medium max-w-56">
                    <span className="flex items-center gap-1.5 min-w-0">
                      <span className="truncate">{lead.name || "Sem nome"}</span>
                      {lead.ai_qualified_at && <BadgeCheck className="w-3.5 h-3.5 shrink-0 text-emerald-600" aria-label="Qualificado pela IA" />}
                    </span>
                    {lead.company && <span className="block text-xs text-muted-foreground truncate">{lead.company}</span>}
                  </TableCell>
                  <TableCell className="whitespace-nowrap tabular-nums">{phoneDisplay(lead.phone)}</TableCell>
                  <TableCell className="whitespace-nowrap">{lead.product ? PRODUCT_LABELS[lead.product] : "—"}</TableCell>
                  <TableCell>
                    <Badge variant="outline" className={`whitespace-nowrap ${LEAD_STATUS_STYLES[lead.customer_state_now] ?? ""}`}>
                      {LEAD_STATUS_LABELS[lead.customer_state_now] ?? lead.customer_state_now}
                    </Badge>
                  </TableCell>
                  <TableCell className="whitespace-nowrap">{OWNER_LABELS[lead.owner || "sdr"]}</TableCell>
                  <TableCell className="whitespace-nowrap">{lead.event_date ? formatDay(lead.event_date) : "—"}</TableCell>
                  <TableCell className="text-right whitespace-nowrap tabular-nums">{value > 0 ? formatBRL(value) : "—"}</TableCell>
                  <TableCell className="whitespace-nowrap text-muted-foreground">
                    {formatDateTime(lead.last_interaction_at || lead.updated_at)}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>
      {hasNextPage && (
        <div className="border-t border-border/50 p-2 flex justify-center">
          <Button variant="ghost" size="sm" onClick={() => fetchNextPage()} disabled={isFetchingNextPage}>
            {isFetchingNextPage ? <Loader2 className="w-4 h-4 animate-spin" /> : `Carregar mais (${total - leads.length})`}
          </Button>
        </div>
      )}
    </div>
  );
}
