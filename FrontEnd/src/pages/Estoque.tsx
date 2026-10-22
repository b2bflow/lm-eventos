import { Fragment, useDeferredValue, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  AlertCircle, ChevronRight, CircleDashed, Info, Loader2, MessageSquareText, Package, PackageX, Plus, Search,
  SlidersHorizontal, Tag, X,
} from "lucide-react";
import { PageShell } from "@/components/shared/PageShell";
import { FilterBar } from "@/components/shared/FilterBar";
import { KpiCard } from "@/components/shared/KpiCard";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import {
  DropdownMenu, DropdownMenuCheckboxItem, DropdownMenuContent, DropdownMenuLabel, DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import api from "@/services/api";
import { cn } from "@/lib/utils";
import { formatBRL } from "@/lib/format";
import { isAdminUser, useCurrentUser } from "@/hooks/useFunnel";
import { useLmSettings } from "@/hooks/useLmSettings";
import { useInventory, type InventoryRow } from "@/hooks/useSales";
import { InventoryItemDrawer } from "@/components/domain/inventory/InventoryItemDrawer";
import { INVENTORY_LINES } from "@/components/domain/inventory/constants";
import { NewInventoryItemDialog } from "@/components/domain/inventory/NewInventoryItemDialog";

const today = () => new Date().toISOString().slice(0, 10);

/** Minúsculas e sem acento: "iluminacao" acha "Iluminação". */
const normalize = (text: string) => text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

const matches = (row: InventoryRow, terms: string[]) => {
  const haystack = normalize(`${row.name} ${row.code} ${row.line}`);
  return terms.every((t) => haystack.includes(t));
};

type Status = "falta" | "pendente" | "sem_preco";

const isPending = (r: InventoryRow) => r.owned && r.qty_total === null;
const STATUS_TEST: Record<Status, (r: InventoryRow) => boolean> = {
  falta: (r) => r.available !== null && r.available <= 0,
  pendente: isPending,
  sem_preco: (r) => r.sale_price === null,
};

const unitLabel = (unit: string) => (unit === "metro" ? "peça" : unit);

/** Nível do disponível: zerado (vermelho), pouco (âmbar, até 20% do total) ou ok. */
function level(row: InventoryRow): "out" | "low" | "ok" {
  if (row.available === null) return "ok";
  if (row.available <= 0) return "out";
  return row.qty_total && row.available / row.qty_total <= 0.2 ? "low" : "ok";
}

function Availability({ row, compact = false }: { row: InventoryRow; compact?: boolean }) {
  if (row.available === null) {
    return <span className="text-xs text-muted-foreground">{row.owned ? "sem contagem" : "sob demanda"}</span>;
  }
  const lvl = level(row);
  const pct = row.qty_total ? Math.max(0, Math.min(100, (row.available / row.qty_total) * 100)) : 0;
  return (
    <div className="flex flex-col items-end gap-1">
      <span className={cn("font-semibold tabular-nums", lvl === "out" && "text-rose-600 dark:text-rose-400",
        lvl === "low" && "text-amber-600 dark:text-amber-400")}>
        {row.available}
        {compact && <span className="text-xs font-normal text-muted-foreground"> de {row.qty_total ?? 0}</span>}
      </span>
      {!compact && (lvl === "low" || !!row.reserved) && (
        <div className="h-1 w-20 rounded-full bg-muted overflow-hidden" aria-hidden>
          <div className={cn("h-full rounded-full", lvl === "out" ? "bg-rose-500" : lvl === "low" ? "bg-amber-500" : "bg-emerald-500")}
            style={{ width: `${pct}%` }} />
        </div>
      )}
    </div>
  );
}

function Flags({ row }: { row: InventoryRow }) {
  const flags: { label: string; tone: "red" | "amber" | "muted" }[] = [];
  if (!row.active) flags.push({ label: "removido", tone: "red" });
  if (isPending(row)) flags.push({ label: "contagem pendente", tone: "amber" });
  if (row.sale_price === null) flags.push({ label: "sem preço", tone: "red" });
  if (!row.owned) flags.push({ label: "terceirizado", tone: "muted" });
  if (!row.rentable) flags.push({ label: "apoio interno", tone: "muted" });
  if (!flags.length) return null;
  return (
    <div className="flex flex-wrap gap-1 mt-1">
      {flags.map((f) => (
        <span key={f.label} className={cn("rounded px-1.5 py-px text-[10px] font-medium leading-4",
          f.tone === "red" && "bg-rose-500/10 text-rose-700 dark:text-rose-300",
          f.tone === "amber" && "bg-amber-500/15 text-amber-800 dark:text-amber-300",
          f.tone === "muted" && "bg-muted text-muted-foreground")}>
          {f.label}
        </span>
      ))}
    </div>
  );
}

function ItemName({ row, wrap = false }: { row: InventoryRow; wrap?: boolean }) {
  return (
    <div className="min-w-0">
      <div className="font-medium flex items-center gap-1.5">
        <span className={wrap ? "line-clamp-2" : "truncate"}>{row.name}</span>
        {row.observations_count > 0 && (
          <span className="inline-flex items-center gap-0.5 text-xs text-muted-foreground shrink-0"
            title={`${row.observations_count} observação(ões)`}>
            <MessageSquareText className="w-3.5 h-3.5" />{row.observations_count}
          </span>
        )}
      </div>
      <Flags row={row} />
    </div>
  );
}

export default function Estoque() {
  const queryClient = useQueryClient();
  const [line, setLine] = useState<string | null>(null);
  const [status, setStatus] = useState<Status | null>(null);
  const [start, setStart] = useState(today());
  const [end, setEnd] = useState(today());
  const [search, setSearch] = useState("");
  const [showRemoved, setShowRemoved] = useState(false);
  const [openItem, setOpenItem] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const deferredSearch = useDeferredValue(search);
  const terms = useMemo(() => normalize(deferredSearch).split(/\s+/).filter(Boolean), [deferredSearch]);
  const searching = terms.length > 0;

  const { data: me } = useCurrentUser();
  const { data: settings } = useLmSettings();
  const reservationsOn = settings?.inventory_reservations_enabled !== false;
  const isAdmin = isAdminUser(me);
  const canEdit = isAdmin || me?.role === "porta";
  // Busca sempre todas as linhas: os contadores das abas e dos alertas saem da mesma lista.
  const { data: rows = [], isLoading } = useInventory(undefined, start, end || start, canEdit && showRemoved);

  const base = useMemo(
    () => rows.filter((r) => (r.rentable || canEdit) && (!searching || matches(r, terms))),
    [rows, canEdit, searching, terms],
  );
  const stats = useMemo(() => ({
    items: base.filter((r) => r.active).length,
    falta: base.filter(STATUS_TEST.falta).length,
    pendente: base.filter(STATUS_TEST.pendente).length,
    sem_preco: base.filter(STATUS_TEST.sem_preco).length,
  }), [base]);
  const byStatus = useMemo(() => (status ? base.filter(STATUS_TEST[status]) : base), [base, status]);
  const lineCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    byStatus.forEach((r) => { counts[r.line] = (counts[r.line] || 0) + 1; });
    return counts;
  }, [byStatus]);
  const visible = line ? byStatus.filter((r) => r.line === line) : byStatus;
  const groups = INVENTORY_LINES.map((l) => ({ line: l, rows: visible.filter((r) => r.line === l) })).filter((g) => g.rows.length);
  const grouped = !line;
  const filtered = searching || !!status || !!line;
  const colSpan = reservationsOn ? 6 : 5;

  const toggleStatus = (next: Status) => setStatus(status === next ? null : next);
  const clearFilters = () => { setSearch(""); setStatus(null); setLine(null); };
  const toggleReservations = async (next: boolean) => {
    try {
      await api.patch("/crm/settings/", { inventory_reservations_enabled: next });
      toast.success(next ? "Reserva de estoque ligada." : "Reserva de estoque desligada.");
      queryClient.invalidateQueries({ queryKey: ["lm-settings"] });
      queryClient.invalidateQueries({ queryKey: ["inventory"] });
      queryClient.invalidateQueries({ queryKey: ["inventory-item"] });
    } catch {
      toast.error("Não foi possível alterar a configuração.");
    }
  };

  const kpi = (key: Status) => ({
    active: status === key,
    onClick: stats[key] > 0 || status === key ? () => toggleStatus(key) : undefined,
    className: cn(status === key && "ring-2 ring-primary border-primary/60", !stats[key] && status !== key && "opacity-60"),
  });

  return (
    <PageShell
      title="Estoque"
      maxWidthClassName="max-w-7xl"
      actions={canEdit ? (
        <Button onClick={() => setCreating(true)}>
          <Plus className="w-4 h-4 sm:mr-2" /> <span className="hidden sm:inline">Novo item</span>
        </Button>
      ) : undefined}
    >
            {/* Busca, período e opções */}
            <FilterBar>
              <div className="relative w-full sm:w-auto">
                <Search className="absolute left-2.5 top-2.5 w-4 h-4 text-muted-foreground" />
                <Input value={search} placeholder="Buscar por nome ou código" onChange={(e) => setSearch(e.target.value)}
                  className="pl-8 pr-8 w-full sm:w-[280px]" />
                {search && (
                  <button className="absolute right-2.5 top-2.5 text-muted-foreground hover:text-foreground"
                    onClick={() => setSearch("")} title="Limpar busca"><X className="w-4 h-4" /></button>
                )}
              </div>
              {reservationsOn ? (
                <div className="flex items-center gap-2 w-full sm:w-auto" title="Período usado para descontar as reservas">
                  <Input type="date" value={start} aria-label="Início do período" className="flex-1 min-w-0 sm:flex-none sm:w-[150px]"
                    onChange={(e) => { setStart(e.target.value); if (e.target.value > end) setEnd(e.target.value); }} />
                  <span className="text-sm text-muted-foreground">até</span>
                  <Input type="date" value={end} min={start} aria-label="Fim do período" className="flex-1 min-w-0 sm:flex-none sm:w-[150px]"
                    onChange={(e) => setEnd(e.target.value)} />
                </div>
              ) : (
                <span className="text-xs text-muted-foreground px-1">Reservas desligadas</span>
              )}
              {canEdit && (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="outline" size="icon" className="shrink-0 relative" title="Opções do estoque">
                      <SlidersHorizontal className="w-4 h-4" />
                      {showRemoved && <span className="absolute top-1.5 right-1.5 w-1.5 h-1.5 rounded-full bg-primary" />}
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="start" className="w-72">
                    <DropdownMenuLabel className="text-xs text-muted-foreground font-normal">Exibição</DropdownMenuLabel>
                    <DropdownMenuCheckboxItem checked={showRemoved} onCheckedChange={(v) => setShowRemoved(!!v)}>
                      Mostrar itens removidos
                    </DropdownMenuCheckboxItem>
                    {isAdmin && (
                      <>
                        <DropdownMenuSeparator />
                        <DropdownMenuLabel className="text-xs text-muted-foreground font-normal">Sistema</DropdownMenuLabel>
                        <label className="flex items-center justify-between gap-3 px-2 py-1.5 text-sm cursor-pointer">
                          <span>
                            Reserva de estoque
                            <span className="block text-xs text-muted-foreground">Descontar propostas aceitas e reservas manuais do disponível</span>
                          </span>
                          <Switch checked={reservationsOn} onCheckedChange={toggleReservations} />
                        </label>
                      </>
                    )}
                  </DropdownMenuContent>
                </DropdownMenu>
              )}
            </FilterBar>

            {/* Resumo: os alertas também filtram a lista */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              <KpiCard label={searching ? "Itens encontrados" : "Itens no estoque"} value={stats.items} icon={Package} tone="primary"
                loading={isLoading} caption={(
                  <span className="inline-flex items-center gap-1"><Info className="w-3 h-3 shrink-0 text-amber-500" /> Contagem aproximada de 22/01/2025</span>
                )} />
              <KpiCard label={reservationsOn ? "Esgotados no período" : "Esgotados"} value={stats.falta} icon={PackageX} tone="danger"
                loading={isLoading} caption={status === "falta" ? "Filtrando · clique para limpar" : "Clique para filtrar"} {...kpi("falta")} />
              <KpiCard label="Contagem pendente" value={stats.pendente} icon={CircleDashed} tone="warning"
                loading={isLoading} caption={status === "pendente" ? "Filtrando · clique para limpar" : "Clique para filtrar"} {...kpi("pendente")} />
              <KpiCard label="Sem preço na tabela" value={stats.sem_preco} icon={Tag} tone="danger"
                loading={isLoading} caption={status === "sem_preco" ? "Filtrando · clique para limpar" : "Clique para filtrar"} {...kpi("sem_preco")} />
            </div>

            {/* Abas por linha */}
            <div className="flex items-center gap-1 overflow-x-auto -mx-4 px-4 md:mx-0 md:px-0 border-b [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
              {[null, ...INVENTORY_LINES].map((l) => {
                const count = l ? lineCounts[l] || 0 : byStatus.length;
                const selected = line === l;
                return (
                  <button key={l ?? "all"} onClick={() => setLine(l)} disabled={!count && !selected}
                    className={cn("whitespace-nowrap px-3 py-2 text-sm transition-colors -mb-px border-b-2",
                      selected ? "border-primary text-foreground font-medium" : "border-transparent text-muted-foreground hover:text-foreground",
                      !count && !selected && "opacity-40")}>
                    {l ?? "Todas"}
                    <span className={cn("ml-1.5 rounded-full px-1.5 text-[11px] tabular-nums",
                      selected ? "bg-primary/10 text-primary" : "bg-muted")}>{count}</span>
                  </button>
                );
              })}
            </div>

            {isLoading ? (
              <div className="flex justify-center py-16"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>
            ) : visible.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-border p-10 text-center space-y-2">
                <AlertCircle className="w-6 h-6 mx-auto text-muted-foreground" />
                <p className="text-sm text-muted-foreground">
                  {searching ? `Nenhum equipamento encontrado para "${search}".` : "Nenhum item com esses filtros."}
                </p>
                {filtered && <Button variant="outline" size="sm" onClick={clearFilters}>Limpar filtros</Button>}
              </div>
            ) : (
              <>
                {/* Telas médias e grandes: tabela agrupada por linha */}
                <div className="hidden md:block glass rounded-2xl border border-border/50 overflow-hidden">
                  <table className="w-full text-sm">
                    <thead className="text-xs text-muted-foreground bg-muted/40">
                      <tr>
                        <th className="text-left font-medium px-4 py-2.5">Item</th>
                        <th className="text-right font-medium px-4 py-2.5">Preço</th>
                        <th className="text-right font-medium px-4 py-2.5">Total</th>
                        {reservationsOn && <th className="text-right font-medium px-4 py-2.5">Reservado</th>}
                        <th className="text-right font-medium px-4 py-2.5">Disponível</th>
                        <th className="w-8" />
                      </tr>
                    </thead>
                    <tbody>
                      {groups.map((group) => (
                        <Fragment key={group.line}>
                          {grouped && (
                            <tr className="bg-muted/20 border-t">
                              <td colSpan={colSpan} className="px-4 py-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                                {group.line}
                                <span className="font-normal normal-case"> · {group.rows.length} {group.rows.length === 1 ? "item" : "itens"}</span>
                              </td>
                            </tr>
                          )}
                          {group.rows.map((row) => (
                            <tr key={row.id} onClick={() => setOpenItem(row.id)}
                              className={cn("group border-t cursor-pointer hover:bg-muted/40 transition-colors", !row.active && "opacity-60")}>
                              <td className="px-4 py-2.5 max-w-0 w-1/2"><ItemName row={row} /></td>
                              <td className="px-4 py-2.5 text-right whitespace-nowrap">
                                {row.sale_price === null ? (
                                  isAdmin
                                    ? <span className="text-xs font-medium text-primary group-hover:underline">+ Adicionar preço</span>
                                    : <span className="text-muted-foreground">—</span>
                                ) : (
                                  <span className="tabular-nums">
                                    {formatBRL(row.sale_price)}
                                    <span className="text-xs text-muted-foreground"> / {unitLabel(row.billing_unit)}</span>
                                  </span>
                                )}
                              </td>
                              <td className="px-4 py-2.5 text-right tabular-nums">
                                {row.owned && row.qty_total !== null ? row.qty_total : <span className="text-muted-foreground">—</span>}
                              </td>
                              {reservationsOn && (
                                <td className={cn("px-4 py-2.5 text-right tabular-nums", !row.reserved && "text-muted-foreground")}>
                                  {row.reserved || 0}
                                </td>
                              )}
                              <td className="px-4 py-2.5"><div className="flex justify-end"><Availability row={row} /></div></td>
                              <td className="pr-3 text-muted-foreground/40 group-hover:text-muted-foreground"><ChevronRight className="w-4 h-4" /></td>
                            </tr>
                          ))}
                        </Fragment>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* Celular: cartões */}
                <div className="md:hidden space-y-4">
                  {groups.map((group) => (
                    <section key={group.line} className="space-y-2">
                      {grouped && (
                        <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                          {group.line} <span className="font-normal normal-case">· {group.rows.length}</span>
                        </h2>
                      )}
                      <ul className="glass rounded-2xl border border-border/50 divide-y divide-border/50 overflow-hidden">
                        {group.rows.map((row) => (
                          <li key={row.id}>
                            <button onClick={() => setOpenItem(row.id)}
                              className={cn("w-full flex items-center gap-3 px-3 py-3 text-left active:bg-muted/50", !row.active && "opacity-60")}>
                              <div className="flex-1 min-w-0">
                                <ItemName row={row} wrap />
                                {row.sale_price !== null && (
                                  <div className="text-xs text-muted-foreground mt-0.5">{formatBRL(row.sale_price)} por {unitLabel(row.billing_unit)}</div>
                                )}
                              </div>
                              <div className="text-right shrink-0">
                                <Availability row={row} compact />
                                {reservationsOn && !!row.reserved && <div className="text-[11px] text-muted-foreground">{row.reserved} reservado</div>}
                              </div>
                              <ChevronRight className="w-4 h-4 text-muted-foreground/60 shrink-0" />
                            </button>
                          </li>
                        ))}
                      </ul>
                    </section>
                  ))}
                </div>
              </>
            )}

      <InventoryItemDrawer itemId={openItem} onClose={() => setOpenItem(null)} canEdit={canEdit} canEditPrice={isAdmin} myId={me?.id} />
      <NewInventoryItemDialog open={creating} onOpenChange={setCreating} defaultLine={line ?? undefined} onCreated={setOpenItem}
        canEditPrice={isAdmin} />
    </PageShell>
  );
}
