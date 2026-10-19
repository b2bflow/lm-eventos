import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Building2, CalendarHeart, DoorOpen, Loader2, Minus, Package, Plus, Save, Search, UserRound, X } from "lucide-react";
import { PageShell } from "@/components/shared/PageShell";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import api from "@/services/api";
import { cn } from "@/lib/utils";
import { formatBRL, phoneDisplay } from "@/lib/format";
import { PRODUCT_LABELS } from "@/constants/mappings";
import { isAdminUser, useCurrentUser, useLead, type FunnelLead } from "@/hooks/useFunnel";
import { useCatalog, useProposal, type QuoteResult } from "@/hooks/useSales";
import { QuoteSummary } from "@/components/domain/sales/QuoteSummary";
import { EventFormFields } from "@/components/domain/sales/EventFormFields";
import { SingleProductFields } from "@/components/domain/sales/SingleProductFields";
import {
  answeredYes, emptyEvent, emptySingleProduct, eventInputs, singleProductInputs, toIsoDay,
  type EventForm, type SingleProductForm,
} from "@/lib/quoteForms";

type Mode = "porta" | "corporativo" | "social" | "produto_unico";

const PORTA_LINES = ["Q30", "Q15", "Acessórios"];
const MODES: Mode[] = ["porta", "corporativo", "social", "produto_unico"];

function useDebounced<T>(value: T, delay: number) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

function LeadPicker({ onPick }: { onPick: (id: string) => void }) {
  const [term, setTerm] = useState("");
  const [focused, setFocused] = useState(false);
  const search = useDebounced(term.trim(), 300);
  const { data = [], isFetching } = useQuery({
    queryKey: ["lead-picker", search],
    queryFn: async () => (await api.get("/crm/customers/", { params: { search, page_size: 8 } })).data.results as FunnelLead[],
    enabled: search.length >= 2,
  });
  const open = focused && search.length >= 2;
  return (
    <div className="relative w-full sm:w-[320px]">
      <Search className="absolute left-2.5 top-2.5 w-4 h-4 text-muted-foreground" />
      <Input value={term} onChange={(e) => setTerm(e.target.value)} onFocus={() => setFocused(true)}
        onBlur={() => window.setTimeout(() => setFocused(false), 150)}
        placeholder="Escolher lead (nome ou telefone)" className="pl-8" />
      {isFetching && <Loader2 className="absolute right-2.5 top-2.5 w-4 h-4 animate-spin text-muted-foreground" />}
      {open && (
        <ul className="absolute z-30 mt-1 w-full rounded-xl border border-border/60 bg-popover shadow-lg divide-y divide-border/50 max-h-64 overflow-y-auto">
          {data.length === 0 && !isFetching && <li className="px-3 py-2 text-sm text-muted-foreground">Nenhum lead encontrado.</li>}
          {data.map((lead) => (
            <li key={lead.id}>
              <button className="w-full text-left px-3 py-2 text-sm hover:bg-muted/60" onMouseDown={(e) => e.preventDefault()}
                onClick={() => onPick(lead.id)}>
                <span className="font-medium text-foreground">{lead.name || "Sem nome"}</span>
                <span className="text-muted-foreground"> · {phoneDisplay(lead.phone)}</span>
                {lead.product && <span className="block text-xs text-muted-foreground">{PRODUCT_LABELS[lead.product]}</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

const MODE_INFO: Record<Mode, { label: string; hint: string; icon: typeof DoorOpen }> = {
  porta: { label: "Locação de porta", hint: "Peças retiradas e devolvidas", icon: DoorOpen },
  corporativo: { label: "Corporativo", hint: "Evento de empresa", icon: Building2 },
  social: { label: "Social", hint: "Casamento, aniversário...", icon: CalendarHeart },
  produto_unico: { label: "Produto único", hint: "Um item avulso", icon: Package },
};

function QtyStepper({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  return (
    <div className="flex items-center rounded-lg border border-border/60 bg-background shrink-0">
      <button type="button" className="w-8 h-9 grid place-items-center text-muted-foreground hover:text-foreground disabled:opacity-30"
        disabled={value <= 0} onClick={() => onChange(Math.max(0, value - 1))} aria-label="Diminuir"><Minus className="w-3.5 h-3.5" /></button>
      <input type="number" min={0} value={value || ""} placeholder="0" aria-label="Quantidade"
        onChange={(e) => onChange(Math.max(0, Number(e.target.value) || 0))}
        className="w-12 h-9 bg-transparent text-center text-sm tabular-nums outline-none [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none" />
      <button type="button" className="w-8 h-9 grid place-items-center text-muted-foreground hover:text-foreground"
        onClick={() => onChange(value + 1)} aria-label="Aumentar"><Plus className="w-3.5 h-3.5" /></button>
    </div>
  );
}

export default function Calculadora() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [params, setParams] = useSearchParams();
  const leadId = params.get("lead");
  const proposalId = params.get("proposal");

  const { data: catalog } = useCatalog();
  const { data: lead } = useLead(leadId);
  const { data: baseProposal } = useProposal(proposalId);
  const { data: me } = useCurrentUser();
  const isAdmin = isAdminUser(me);

  const [mode, setMode] = useState<Mode>("porta");
  const [pickup, setPickup] = useState("");
  const [returnDate, setReturnDate] = useState("");
  const [items, setItems] = useState<Record<string, number>>({});
  const [events, setEvents] = useState<Record<"corporativo" | "social", EventForm>>(() => ({
    corporativo: emptyEvent("corporativo"), social: emptyEvent("social"),
  }));
  const [single, setSingle] = useState<SingleProductForm>(emptySingleProduct);
  const [itemFilter, setItemFilter] = useState("Q30");
  const patchEvent = (variant: "corporativo" | "social") => (patch: Partial<EventForm>) =>
    setEvents((e) => ({ ...e, [variant]: { ...e[variant], ...patch } }));

  // Pré-preenche com a qualificação do lead
  useEffect(() => {
    if (!lead || proposalId) return;
    const q = lead.qualification || {};
    const attachmentKinds = new Set((lead.attachments || []).map((a) => a.kind));
    if (lead.product === "corporativo") setMode("corporativo");
    if (lead.product === "social") setMode("social");
    if (lead.product === "produto_unico") setMode("produto_unico");
    if (lead.product === "estrutura_porta" || lead.product === "estrutura_montagem") setMode("porta");
    setPickup(toIsoDay(q.data_retirada) || "");
    setReturnDate(toIsoDay(q.data_devolucao) || "");
    const eventDay = toIsoDay(lead.event_date);
    setEvents((e) => ({
      corporativo: { ...e.corporativo, guests: lead.guest_count || e.corporativo.guests, event_date: eventDay || e.corporativo.event_date },
      social: {
        ...e.social, guests: lead.guest_count || e.social.guests, event_date: eventDay || e.social.event_date,
        dj: q.dj === undefined ? e.social.dj : answeredYes(q.dj),
        ceremony_sound: answeredYes(q.cerimonia) || e.social.ceremony_sound,
        has_project: answeredYes(q.projeto) || attachmentKinds.has("projeto"),
        competitor_quote: answeredYes(q.orcamento_concorrente) || attachmentKinds.has("orcamento_concorrente"),
      },
    }));
    setSingle((f) => ({
      ...f,
      event_date: toIsoDay(q.data_uso) || eventDay || f.event_date,
      delivery: typeof q.forma_entrega === "string" && /entreg/i.test(q.forma_entrega) ? "entrega" : f.delivery,
      assembly: answeredYes(q.precisa_montagem) || f.assembly,
    }));
  }, [lead, proposalId]);

  // Abrindo uma proposta existente: carrega as entradas (salvar gera nova versão)
  useEffect(() => {
    if (!baseProposal) return;
    const inputs = baseProposal.inputs as Record<string, unknown>;
    if (baseProposal.mode === "porta") {
      setMode("porta");
      setPickup(String(inputs.pickup_date || ""));
      setReturnDate(String(inputs.return_date || ""));
      const list = (inputs.items as { code: string; qty: number }[]) || [];
      setItems(Object.fromEntries(list.map((i) => [i.code, i.qty])));
    } else if (baseProposal.mode === "corporativo" || baseProposal.mode === "social") {
      const variant = baseProposal.mode;
      setMode(variant);
      setEvents((e) => ({ ...e, [variant]: { ...emptyEvent(variant), ...(inputs as Partial<EventForm>) } }));
    } else if (baseProposal.mode === "produto_unico") {
      setMode("produto_unico");
      const list = (inputs.items as { code: string; qty: number }[]) || [];
      setSingle({
        ...emptySingleProduct(), ...(inputs as Partial<SingleProductForm>),
        end_date: String(inputs.end_date || ""), items: Object.fromEntries(list.map((i) => [i.code, i.qty])),
      });
    }
  }, [baseProposal]);

  const inputs = useMemo(() => {
    if (mode === "porta") {
      return {
        pickup_date: pickup, return_date: returnDate,
        items: Object.entries(items).filter(([, q]) => q > 0).map(([code, qty]) => ({ code, qty })),
      };
    }
    if (mode === "produto_unico") return singleProductInputs(single, isAdmin);
    return eventInputs(mode, events[mode], isAdmin);
  }, [mode, pickup, returnDate, items, events, single, isAdmin]);

  const debouncedInputs = useDebounced(inputs, 500);
  const ready = mode === "porta"
    ? !!pickup && !!returnDate && (inputs as { items: unknown[] }).items.length > 0
    : mode === "produto_unico"
      ? !!single.event_date && (inputs as { items: unknown[] }).items.length > 0
      : events[mode].guests > 0 && (!!events[mode].event_date || !!lead?.event_date);

  const preview = useQuery({
    queryKey: ["quote-preview", mode, debouncedInputs, leadId, proposalId],
    queryFn: async () =>
      (await api.post<QuoteResult>("/sales/proposals/calculate/", {
        mode, inputs: debouncedInputs, customer_id: leadId || undefined, replaces: proposalId || undefined,
      })).data,
    enabled: ready,
    retry: false,
  });
  const previewError = (preview.error as { response?: { data?: { detail?: string } } } | null)?.response?.data?.detail;

  const save = useMutation({
    mutationFn: async () =>
      (await api.post("/sales/proposals/", { customer_id: leadId, mode, inputs, replaces: proposalId || undefined })).data,
    onSuccess: (proposal: { status: string; version: number }) => {
      toast.success(proposal.status === "aguardando_aprovacao"
        ? `Proposta v${proposal.version} salva e enviada para aprovação da Erica.`
        : `Proposta v${proposal.version} salva.`);
      queryClient.invalidateQueries({ queryKey: ["proposals", leadId] });
      queryClient.invalidateQueries({ queryKey: ["funnel"] });
      navigate(`/funil?lead=${leadId}`);
    },
    onError: (error) => toast.error((error as { response?: { data?: { detail?: string } } }).response?.data?.detail || "Não foi possível salvar."),
  });

  const allPortaItems = (catalog?.items || []).filter((i) => PORTA_LINES.includes(i.line));
  const portaItems = allPortaItems.filter((i) => i.line === itemFilter);
  const selectedPorta = allPortaItems.filter((i) => (items[i.code] || 0) > 0);
  const lineCount = (line: string) => allPortaItems.filter((i) => i.line === line && (items[i.code] || 0) > 0).length;

  return (
    <PageShell
      title="Calculadora de proposta"
      maxWidthClassName="max-w-7xl"
    >
      {/* Para quem e qual tipo de proposta */}
      <div className="glass rounded-2xl border border-border/50 p-3 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap items-center gap-2 min-w-0">
          {lead ? (
            <div className="flex items-center gap-3 min-w-0 rounded-xl border border-border/60 bg-card px-3 py-2">
              <span className="w-8 h-8 rounded-full bg-primary/10 text-primary grid place-items-center shrink-0"><UserRound className="w-4 h-4" /></span>
              <span className="min-w-0">
                <span className="block text-sm font-semibold text-foreground truncate">{lead.name || phoneDisplay(lead.phone)}</span>
                <span className="block text-xs text-muted-foreground truncate">
                  {phoneDisplay(lead.phone)}{lead.product ? ` · ${PRODUCT_LABELS[lead.product]}` : ""}
                </span>
              </span>
              <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0" title="Trocar lead" onClick={() => setParams({})}><X className="w-4 h-4" /></Button>
            </div>
          ) : (
            <LeadPicker onPick={(id) => setParams({ lead: id })} />
          )}
          {baseProposal ? (
            <StatusBadge tone="info" className="whitespace-normal">Editando a proposta v{baseProposal.version}: salvar gera uma nova versão</StatusBadge>
          ) : !leadId ? (
            <span className="text-xs text-muted-foreground">Sem lead, a calculadora só simula.</span>
          ) : null}
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-1 rounded-xl bg-muted p-1">
          {MODES.map((m) => {
            const info = MODE_INFO[m];
            const Icon = info.icon;
            return (
              <button key={m} type="button" onClick={() => setMode(m)} title={info.hint}
                className={cn("flex items-center justify-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors whitespace-nowrap",
                  mode === m ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground")}>
                <Icon className="w-4 h-4 shrink-0" /> {info.label}
              </button>
            );
          })}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_380px] gap-4 items-start">
        <div className="glass rounded-2xl border border-border/50 p-4 sm:p-5 space-y-4">
          <div>
            <h2 className="text-base font-semibold text-foreground">{MODE_INFO[mode].label}</h2>
            <p className="text-xs text-muted-foreground">Sem desconto pela SDR: qualquer exceção vai para a Erica.</p>
          </div>
          {mode === "porta" ? (
            <>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="space-y-1">
                  <Label className="text-xs">Retirada</Label>
                  <Input type="date" value={pickup} onChange={(e) => setPickup(e.target.value)} />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Devolução</Label>
                  <Input type="date" value={returnDate} min={pickup || undefined} onChange={(e) => setReturnDate(e.target.value)} />
                </div>
              </div>
              <p className="text-xs text-muted-foreground">Período base: 1 final de semana (até 7 dias). Acima disso, multiplica por semana e vai para aprovação.</p>

              <section className="border-t border-border/50 pt-4 space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Peças</h3>
                  {selectedPorta.length > 0 && (
                    <button type="button" className="text-xs text-muted-foreground hover:text-foreground" onClick={() => setItems({})}>
                      Limpar seleção ({selectedPorta.length})
                    </button>
                  )}
                </div>
                <div className="flex items-center gap-1 border-b border-border/50">
                  {PORTA_LINES.map((line) => {
                    const count = lineCount(line);
                    return (
                      <button key={line} type="button" onClick={() => setItemFilter(line)}
                        className={cn("px-3 py-2 text-sm -mb-px border-b-2 transition-colors",
                          itemFilter === line ? "border-primary text-foreground font-medium" : "border-transparent text-muted-foreground hover:text-foreground")}>
                        {line}
                        {count > 0 && <span className="ml-1.5 rounded-full bg-primary/10 text-primary px-1.5 text-[11px] tabular-nums">{count}</span>}
                      </button>
                    );
                  })}
                </div>
                <ul className="rounded-xl border border-border/50 divide-y divide-border/50 overflow-hidden">
                  {portaItems.map((item) => {
                    const qty = items[item.code] || 0;
                    return (
                      <li key={item.code} className={cn("flex items-center justify-between gap-3 px-3 py-2 bg-card", qty > 0 && "bg-primary/5")}>
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-foreground">{item.name}</p>
                          <p className="text-xs text-muted-foreground">
                            {item.sale_price === null ? <span className="text-amber-600 dark:text-amber-400">sem preço (vai para aprovação)</span> : `${formatBRL(item.sale_price)} / peça`}
                            {item.note ? ` · ${item.note}` : ""}
                          </p>
                        </div>
                        <QtyStepper value={qty} onChange={(v) => setItems({ ...items, [item.code]: v })} />
                      </li>
                    );
                  })}
                </ul>
              </section>
            </>
          ) : mode === "produto_unico" ? (
            <SingleProductFields form={single} onChange={(patch) => setSingle((f) => ({ ...f, ...patch }))}
              catalog={catalog} isAdmin={isAdmin} />
          ) : (
            <EventFormFields key={mode} variant={mode} form={events[mode]} onChange={patchEvent(mode)}
              catalog={catalog} isAdmin={isAdmin} />
          )}
        </div>

        <div className="space-y-3 lg:sticky lg:top-0">
          {mode === "porta" && selectedPorta.length > 0 && (
            <div className="glass rounded-2xl border border-border/50 p-4">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">Selecionado</h3>
              <ul className="space-y-1 text-sm">
                {selectedPorta.map((i) => (
                  <li key={i.code} className="flex justify-between gap-2">
                    <span className="truncate text-foreground">{i.name}</span>
                    <span className="tabular-nums text-muted-foreground shrink-0">{items[i.code]}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          <QuoteSummary result={ready ? preview.data : undefined} loading={preview.isFetching} error={ready ? previewError : null} />
          <Button className="w-full" size="lg" disabled={!leadId || !ready || !preview.data || save.isPending} onClick={() => save.mutate()}>
            {save.isPending ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Save className="w-4 h-4 mr-2" />}
            {preview.data?.requires_meeting ? "Salvar e chamar a Erica" : preview.data?.locked ? "Salvar e pedir aprovação" : "Salvar proposta"}
          </Button>
          {!leadId && <p className="text-xs text-muted-foreground text-center">Escolha um lead acima para salvar.</p>}
        </div>
      </div>
    </PageShell>
  );
}
