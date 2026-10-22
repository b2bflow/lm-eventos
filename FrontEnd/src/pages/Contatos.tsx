import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { FileUp, Info, Loader2, Search, UserPlus, X } from "lucide-react";
import { PageShell } from "@/components/shared/PageShell";
import { FilterBar } from "@/components/shared/FilterBar";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { ResponsiveTable, type ResponsiveColumn } from "@/components/shared/ResponsiveTable";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  CONTACT_TYPE_LABELS, LEAD_STAGE_TONES, LEAD_STATUS_LABELS, OWNER_LABELS, PRODUCT_LABELS,
} from "@/constants/mappings";
import { formatDay, phoneDisplay } from "@/lib/format";
import { isAdminUser, useCurrentUser } from "@/hooks/useFunnel";
import { useContacts, type ContactFilters, type ContactSummary } from "@/hooks/useContacts";
import { ContactDetailsDialog } from "@/components/domain/contacts/ContactDetailsDialog";
import { ImportPartnersDialog, NewContactDialog } from "@/components/domain/contacts/ContactDialogs";

const ALL = "__all__";

const PARTNER_OPTIONS: Record<string, string> = { yes: "Só parceiros", no: "Sem parceiros" };

function FilterSelect({ value, onChange, placeholder, options }: {
  value?: string; onChange: (v?: string) => void; placeholder: string; options: Record<string, string>;
}) {
  return (
    <Select value={value ?? ALL} onValueChange={(v) => onChange(v === ALL ? undefined : v)}>
      <SelectTrigger className="w-full sm:w-auto sm:min-w-[170px] gap-2"><SelectValue placeholder={placeholder} /></SelectTrigger>
      <SelectContent>
        <SelectItem value={ALL}>{placeholder}</SelectItem>
        {Object.entries(options).map(([key, label]) => <SelectItem key={key} value={key}>{label}</SelectItem>)}
      </SelectContent>
    </Select>
  );
}

const initials = (name?: string | null) =>
  (name || "?").trim().split(/\s+/).slice(0, 2).map((w) => w[0]?.toUpperCase() ?? "").join("") || "?";

const COLUMNS: ResponsiveColumn<ContactSummary>[] = [
  {
    id: "contato", header: "Contato", primary: true,
    cell: (c) => (
      <span className="flex items-center gap-3 min-w-0">
        <span className="w-9 h-9 rounded-full bg-primary/10 text-primary text-xs font-semibold grid place-items-center shrink-0">{initials(c.name)}</span>
        <span className="min-w-0">
          <span className="block font-medium text-foreground truncate">{c.name || "Sem nome"}</span>
          <span className="block text-xs text-muted-foreground truncate">{c.company || <span className="lg:hidden">{phoneDisplay(c.phone)}</span>}</span>
        </span>
      </span>
    ),
  },
  { id: "telefone", header: "Telefone", cell: (c) => <span className="tabular-nums whitespace-nowrap">{phoneDisplay(c.phone)}</span>, className: "hidden lg:table-cell" },
  {
    id: "tipo", header: "Tipo",
    cell: (c) => (
      <span className="flex flex-wrap gap-1">
        <StatusBadge tone={c.contact_type === "parceiro" ? "ai" : c.contact_type === "cliente" ? "success" : "neutral"} dot={false}>
          {CONTACT_TYPE_LABELS[c.contact_type] || c.contact_type}
        </StatusBadge>
        {c.human_operator && <StatusBadge tone="danger" dot={false}>Erica</StatusBadge>}
      </span>
    ),
  },
  {
    id: "lead", header: "Lead atual",
    cell: (c) => c.current_lead ? (
      <span className="flex flex-wrap items-center gap-1.5">
        <StatusBadge tone={LEAD_STAGE_TONES[c.current_lead.stage] ?? "neutral"}>{LEAD_STATUS_LABELS[c.current_lead.stage]}</StatusBadge>
        {c.current_lead.product && <span className="text-xs text-muted-foreground">{PRODUCT_LABELS[c.current_lead.product]}</span>}
      </span>
    ) : <span className="text-xs text-muted-foreground">Fora do funil</span>,
  },
  { id: "leads", header: "Leads", align: "right", cell: (c) => c.leads_count ?? 0, className: "hidden md:table-cell w-20" },
  { id: "atualizado", header: "Atualizado", cell: (c) => <span className="text-muted-foreground whitespace-nowrap">{formatDay(c.updated_at)}</span>, hideOnMobile: true, className: "hidden xl:table-cell" },
];

export default function Contatos() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [searchInput, setSearchInput] = useState("");
  const [filters, setFilters] = useState<ContactFilters>({});
  const [newOpen, setNewOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const openId = searchParams.get("contato");
  const { data: me } = useCurrentUser();
  const canImport = isAdminUser(me) || me?.role === "b2bflow";

  useEffect(() => {
    const timer = window.setTimeout(() => setFilters((f) => ({ ...f, search: searchInput.trim() || undefined })), 400);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  const { data, isLoading, fetchNextPage, hasNextPage, isFetchingNextPage } = useContacts(filters);
  const contacts = data?.pages.flatMap((page) => page.results) ?? [];
  const total = data?.pages[0]?.count ?? 0;

  const openContact = (id: string | null) => {
    const next = new URLSearchParams(searchParams);
    if (id) next.set("contato", id);
    else next.delete("contato");
    setSearchParams(next, { replace: true });
  };

  const filtered = !!(filters.search || filters.contact_type || filters.owner || filters.partner !== undefined);

  return (
    <PageShell
      title="Contatos"
      maxWidthClassName="max-w-7xl"
      actions={(
        <>
          {canImport && (
            <Button variant="outline" onClick={() => setImportOpen(true)} title="Importar parceiros">
              <FileUp className="w-4 h-4 sm:mr-2" /> <span className="hidden sm:inline">Importar parceiros</span>
            </Button>
          )}
          <Button onClick={() => setNewOpen(true)}>
            <UserPlus className="w-4 h-4 sm:mr-2" /> <span className="hidden sm:inline">Novo contato</span>
          </Button>
        </>
      )}
    >
      <FilterBar right={<span className="text-sm text-muted-foreground whitespace-nowrap">{total} contato{total === 1 ? "" : "s"}</span>}>
        <div className="relative w-full sm:w-auto">
          <Search className="absolute left-2.5 top-2.5 w-4 h-4 text-muted-foreground" />
          <Input value={searchInput} onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Nome, telefone, empresa ou e-mail" className="pl-8 w-full sm:w-[280px]" />
        </div>
        <FilterSelect value={filters.contact_type} onChange={(contact_type) => setFilters({ ...filters, contact_type })}
          placeholder="Todos os tipos" options={CONTACT_TYPE_LABELS} />
        <FilterSelect value={filters.owner} onChange={(owner) => setFilters({ ...filters, owner })}
          placeholder="Todos os responsáveis" options={OWNER_LABELS} />
        <FilterSelect
          value={filters.partner === undefined ? undefined : filters.partner ? "yes" : "no"}
          onChange={(v) => setFilters({ ...filters, partner: v === undefined ? undefined : v === "yes" })}
          placeholder="Parceiros e leads" options={PARTNER_OPTIONS}
        />
        {filtered && (
          <Button variant="ghost" size="sm" onClick={() => { setSearchInput(""); setFilters({}); }}>
            <X className="w-4 h-4 mr-1" /> Limpar
          </Button>
        )}
      </FilterBar>

      <div className="glass rounded-2xl border border-border/50 overflow-hidden">
        <ResponsiveTable
          columns={COLUMNS}
          rows={contacts}
          getId={(c) => c.id}
          onRowClick={(c) => openContact(c.id)}
          loading={isLoading}
          emptyText={filtered ? "Nenhum contato com esses filtros." : "Nenhum contato ainda."}
        />
        {hasNextPage && (
          <div className="flex justify-center px-4 py-3 border-t border-border/50">
            <Button variant="outline" size="sm" disabled={isFetchingNextPage} onClick={() => fetchNextPage()}>
              {isFetchingNextPage && <Loader2 className="w-4 h-4 mr-1 animate-spin" />} Carregar mais
            </Button>
          </div>
        )}
      </div>

      <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
        <Info className="w-3.5 h-3.5 mt-px shrink-0" />
        <span>
          O mesmo celular com e sem o nono dígito é tratado como um contato só. Parceiros ficam com a Erica:
          não entram na fila da SDR e a assistente virtual não responde.
        </span>
      </p>

      <ContactDetailsDialog contactId={openId} onClose={() => openContact(null)} />
      <NewContactDialog open={newOpen} onClose={() => setNewOpen(false)}
        onCreated={(id) => { setNewOpen(false); openContact(id); }} />
      <ImportPartnersDialog open={importOpen} onClose={() => setImportOpen(false)} />
    </PageShell>
  );
}
