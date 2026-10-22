import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  ArrowLeft, BadgeCheck, Calculator, CalendarPlus, Check, CheckCircle2, Contact, FileText, Loader2, MessageSquare, Pencil,
  Phone, PhoneCall, Send, ThumbsDown, ThumbsUp, Trophy, XCircle,
} from "lucide-react";
import { PageShell } from "@/components/shared/PageShell";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import api from "@/services/api";
import {
  FLAG_LABELS, LEAD_STATUS_LABELS, LEAD_STATUS_OPTIONS, LEAD_STATUS_STYLES, LOST_REASON_LABELS, ORIGIN_LABELS,
  OWNER_LABELS, PRODUCT_LABELS, PROPOSAL_MODE_LABELS, type LeadStage,
} from "@/constants/mappings";
import { openProposalPdf } from "@/hooks/useSales";
import { useContact } from "@/hooks/useContacts";
import { useMessages } from "@/hooks/useConversations";
import { formatBRL, formatDateTime, formatDay, isOverdue, phoneDisplay, utcIso } from "@/lib/format";
import { toIsoDay } from "@/lib/quoteForms";
import {
  ACTIVITY_TYPES, isAdminUser, useCurrentUser, useLead, useLeadActions, useLeadTasks, useProposals, useTimeline,
  type FunnelLead,
} from "@/hooks/useFunnel";
import { AttachmentView } from "@/components/domain/funnel/AttachmentView";
import { CallDialog, LostReasonDialog } from "@/components/domain/funnel/LeadDialogs";

// Campos da qualificação já exibidos pelos campos do CRM (espelhados no backend)
const MIRRORED_FIELDS = new Set(["nome", "email", "empresa", "cargo", "local", "data_evento", "publico"]);
const STEPS: LeadStage[] = LEAD_STATUS_OPTIONS.filter((s) => s !== "LOST");
const NONE = "__none__";

function toLocalInput(value?: string | null): string {
  if (!value) return "";
  const d = new Date(utcIso(value));
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function Card({ title, children, action }: { title: string; children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <section className="glass rounded-2xl border border-border/50 p-4 space-y-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">{title}</h3>
        {action}
      </div>
      {children}
    </section>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-3 text-sm">
      <dt className="text-muted-foreground shrink-0">{label}</dt>
      <dd className="text-right break-words min-w-0">{children || "—"}</dd>
    </div>
  );
}

/** Faixa com as etapas do funil: clicar muda a etapa (as mesmas regras do quadro). */
function StageStepper({ stage, onChange }: { stage: string; onChange: (stage: LeadStage) => void }) {
  const current = STEPS.indexOf(stage as LeadStage);
  return (
    <div className="flex rounded-xl overflow-hidden border border-border/60 bg-muted/40" role="list" aria-label="Etapas do funil">
      {STEPS.map((step, i) => {
        const done = current >= 0 && i < current;
        const active = i === current;
        return (
          <button key={step} type="button" role="listitem" onClick={() => !active && onChange(step)}
            aria-current={active ? "step" : undefined}
            className={cn(
              "flex-1 min-w-0 px-2 py-2 text-xs sm:text-sm font-medium transition-colors border-r border-border/40 last:border-r-0 truncate",
              active ? "bg-primary text-primary-foreground" : done ? "bg-primary/15 text-foreground" : "text-muted-foreground hover:bg-muted",
            )}>
            {done && <Check className="inline w-3.5 h-3.5 mr-1 -mt-0.5" />}
            {LEAD_STATUS_LABELS[step]}
          </button>
        );
      })}
    </div>
  );
}

type EditForm = {
  name: string; company: string; email: string; role: string; product: string; owner: string; origin: string;
  event_date: string; guest_count: string; venue: string; quoted_amount: string; contract_value: string;
};

const toEditForm = (lead: FunnelLead): EditForm => ({
  name: lead.name || "", company: lead.company || "", email: lead.email || "", role: lead.role || "",
  product: lead.product || "", owner: lead.owner || "sdr", origin: lead.origin || "",
  event_date: toIsoDay(lead.event_date), guest_count: lead.guest_count ? String(lead.guest_count) : "",
  venue: lead.venue || "", quoted_amount: lead.quoted_amount ? String(lead.quoted_amount) : "",
  contract_value: lead.contract_value ? String(lead.contract_value) : "",
});

function EditLeadDialog({ lead, open, onClose }: { lead: FunnelLead; open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<EditForm>(toEditForm(lead));
  const [saving, setSaving] = useState(false);
  useEffect(() => { if (open) setForm(toEditForm(lead)); }, [open, lead]);

  const save = async () => {
    setSaving(true);
    try {
      await api.patch(`/crm/customers/${lead.id}/`, {
        ...form, guest_count: form.guest_count || null, quoted_amount: form.quoted_amount || null,
        contract_value: form.contract_value || null, event_date: form.event_date || null,
      });
      toast.success("Lead atualizado.");
      queryClient.invalidateQueries({ queryKey: ["lead", lead.id] });
      queryClient.invalidateQueries({ queryKey: ["funnel"] });
      queryClient.invalidateQueries({ queryKey: ["lead-timeline", lead.id] });
      onClose();
    } catch (e) {
      toast.error((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "Não foi possível salvar.");
    } finally {
      setSaving(false);
    }
  };

  const text = (key: keyof EditForm, label: string, props: React.InputHTMLAttributes<HTMLInputElement> = {}) => (
    <div className="space-y-1">
      <Label htmlFor={`edit-${key}`} className="text-xs">{label}</Label>
      <Input id={`edit-${key}`} value={form[key]} onChange={(e) => setForm({ ...form, [key]: e.target.value })} {...props} />
    </div>
  );
  const select = (key: "product" | "owner" | "origin", label: string, options: Record<string, string>, optional: boolean) => (
    <div className="space-y-1">
      <Label className="text-xs">{label}</Label>
      <Select value={form[key] || NONE} onValueChange={(v) => setForm({ ...form, [key]: v === NONE ? "" : v })}>
        <SelectTrigger><SelectValue /></SelectTrigger>
        <SelectContent>
          {optional && <SelectItem value={NONE}>Não informado</SelectItem>}
          {Object.entries(options).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}
        </SelectContent>
      </Select>
    </div>
  );

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader><DialogTitle>Editar lead</DialogTitle></DialogHeader>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {text("name", "Nome")}
          {text("company", "Empresa")}
          {text("email", "E-mail", { type: "email" })}
          {text("role", "Cargo")}
          {select("product", "Produto", PRODUCT_LABELS, true)}
          {select("owner", "Responsável", OWNER_LABELS, false)}
          {select("origin", "Origem", ORIGIN_LABELS, true)}
          {text("event_date", "Data do evento", { type: "date" })}
          {text("guest_count", "Público", { type: "number", min: 0 })}
          {text("venue", "Local")}
          {text("quoted_amount", "Valor orçado (R$)", { type: "number", min: 0, step: 0.01 })}
          {text("contract_value", "Valor fechado (R$)", { type: "number", min: 0, step: 0.01 })}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>Cancelar</Button>
          <Button onClick={save} disabled={saving || !form.name.trim()}>{saving && <Loader2 className="w-4 h-4 mr-1 animate-spin" />}Salvar</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ActivitiesTab({ leadId }: { leadId: string }) {
  const { data: pending = [] } = useLeadTasks(leadId);
  const { data: timeline = [] } = useTimeline(leadId);
  const actions = useLeadActions(leadId);
  const today = new Date().toISOString().slice(0, 10);
  const [form, setForm] = useState({ type: "atividade_ligacao", title: "", date: today, time: "09:00" });
  const [note, setNote] = useState("");

  const create = () => {
    if (!form.title.trim() || !form.date) return;
    const due = new Date(`${form.date}T${form.time || "09:00"}`);
    actions.createActivity({ type: form.type, title: form.title, due_at: due.toISOString() })
      .then(() => setForm((f) => ({ ...f, title: "" })))
      .catch(() => undefined);
  };

  return (
    <div className="space-y-4">
      <Card title="Nova atividade">
        <div className="grid grid-cols-1 sm:grid-cols-[160px_minmax(0,1fr)_150px_110px_auto] gap-2 items-end">
          <div className="space-y-1">
            <Label className="text-xs">Tipo</Label>
            <Select value={form.type} onValueChange={(type) => setForm({ ...form, type })}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>{Object.entries(ACTIVITY_TYPES).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="activity-title" className="text-xs">Título</Label>
            <Input id="activity-title" value={form.title} placeholder="Ex.: ligar para confirmar a data"
              onChange={(e) => setForm({ ...form, title: e.target.value })} onKeyDown={(e) => e.key === "Enter" && create()} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="activity-date" className="text-xs">Data</Label>
            <Input id="activity-date" type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="activity-time" className="text-xs">Hora</Label>
            <Input id="activity-time" type="time" value={form.time} onChange={(e) => setForm({ ...form, time: e.target.value })} />
          </div>
          <Button onClick={create} disabled={!form.title.trim() || !form.date || actions.isPending}>Criar</Button>
        </div>
      </Card>

      <Card title={`Pendentes (${pending.length})`}>
        {pending.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nenhuma atividade pendente.</p>
        ) : (
          <ul className="space-y-1.5">
            {pending.map((task) => (
              <li key={task.id} className="flex items-center justify-between gap-2 text-sm rounded-lg border border-border/60 bg-card px-3 py-2">
                <span className="min-w-0">
                  <span className="block truncate">{task.label}</span>
                  <span className={cn("text-xs", isOverdue(task.due_at) ? "text-rose-600 font-semibold" : "text-muted-foreground")}>
                    {isOverdue(task.due_at) ? "Atrasada · " : ""}{formatDateTime(task.due_at)}
                  </span>
                </span>
                <Button size="sm" variant="outline" className="shrink-0" onClick={() => actions.completeTask(task.id).catch(() => undefined)}>
                  <CheckCircle2 className="w-4 h-4 mr-1" /> Concluir
                </Button>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card title="Nota interna">
        <Textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="Visível só para a equipe" />
        <Button size="sm" disabled={!note.trim()} onClick={() => actions.addNote(note).then(() => setNote("")).catch(() => undefined)}>
          <MessageSquare className="w-4 h-4 mr-1" /> Adicionar nota
        </Button>
      </Card>

      <Card title="Histórico">
        {timeline.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nada registrado ainda.</p>
        ) : (
          <ol className="space-y-2 border-l border-border pl-4">
            {timeline.map((entry) => (
              <li key={entry.id} className="text-sm">
                <span className="text-xs text-muted-foreground">{formatDateTime(entry.created_at)}</span>
                <p className="whitespace-pre-wrap break-words">{entry.description}</p>
              </li>
            ))}
          </ol>
        )}
      </Card>
    </div>
  );
}

function ProposalsTab({ lead }: { lead: FunnelLead }) {
  const navigate = useNavigate();
  const { data: proposals = [] } = useProposals(lead.id);
  const { data: me } = useCurrentUser();
  const actions = useLeadActions(lead.id);
  const isAdmin = isAdminUser(me);

  return (
    <Card title={`Propostas (${proposals.length})`}
      action={<Button size="sm" onClick={() => navigate(`/calculadora?lead=${lead.id}`)}><Calculator className="w-4 h-4 mr-1" /> Nova proposta</Button>}>
      {proposals.length === 0 ? (
        <p className="text-sm text-muted-foreground">Nenhuma proposta ainda.</p>
      ) : (
        <ul className="space-y-2">
          {proposals.map((p) => (
            <li key={p.id} className="rounded-lg border border-border/60 bg-card p-3 space-y-2">
              <div className="flex items-center justify-between gap-2 text-sm">
                <span className="font-semibold">v{p.version} · {PROPOSAL_MODE_LABELS[p.mode] || p.mode}</span>
                <span className="font-bold tabular-nums">{formatBRL(p.total)}</span>
              </div>
              <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                <Badge variant={p.status === "aguardando_aprovacao" ? "destructive" : "secondary"}>{p.status_label}</Badge>
                <span>Criada em {formatDateTime(p.created_at)}</span>
                {p.valid_until && <span>· Válida até {formatDateTime(p.valid_until)}</span>}
              </div>
              {p.lock_reasons.length > 0 && (
                <ul className="text-xs text-rose-600 list-disc pl-4">
                  {p.lock_reasons.map((r, i) => <li key={i}>{r.message}{r.detail ? `: ${r.detail}` : ""}</li>)}
                </ul>
              )}
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="ghost" onClick={() => navigate(`/calculadora?lead=${lead.id}&proposal=${p.id}`)}>Abrir</Button>
                <Button size="sm" variant="ghost" onClick={() => openProposalPdf(p.id).catch(() => toast.error("Não foi possível gerar o PDF."))}>
                  <FileText className="w-4 h-4 mr-1" /> PDF
                </Button>
                {isAdmin && p.status === "aguardando_aprovacao" && (
                  <>
                    <Button size="sm" onClick={() => actions.proposalAction(p.id, "approve", { approve: true }).catch(() => undefined)}>
                      <ThumbsUp className="w-4 h-4 mr-1" /> Aprovar
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => actions.proposalAction(p.id, "approve", { approve: false }).catch(() => undefined)}>
                      <ThumbsDown className="w-4 h-4 mr-1" /> Recusar
                    </Button>
                  </>
                )}
                {(p.status === "rascunho" || p.status === "aprovada") && (
                  <>
                    <Button size="sm" disabled={actions.isPending} onClick={() => actions.sendProposalWhatsApp(p.id).catch(() => undefined)}>
                      <Send className="w-4 h-4 mr-1" /> Enviar no WhatsApp
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => actions.proposalAction(p.id, "send").catch(() => undefined)}>Marcar enviada</Button>
                  </>
                )}
                {p.status === "enviada" && (
                  <>
                    <Button size="sm" onClick={() => actions.proposalAction(p.id, "accept").catch(() => undefined)}>
                      <CheckCircle2 className="w-4 h-4 mr-1" /> Aceita
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => actions.proposalAction(p.id, "reject").catch(() => undefined)}>Recusada</Button>
                  </>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function WhatsAppTab({ lead }: { lead: FunnelLead }) {
  const navigate = useNavigate();
  const { data: contact } = useContact(lead.id);
  const conversationId = contact?.conversation_id ?? null;
  const { messages, isLoading, hasNextPage, fetchNextPage, isFetchingNextPage } = useMessages(conversationId, lead.id, true);

  return (
    <Card title="Conversa no WhatsApp"
      action={conversationId && (
        <Button size="sm" variant="outline" onClick={() => navigate(`/whatsapp?conversa=${conversationId}`)}>
          <MessageSquare className="w-4 h-4 mr-1" /> Abrir no WhatsApp
        </Button>
      )}>
      {!contact ? (
        <div className="flex justify-center py-6"><Loader2 className="w-5 h-5 animate-spin text-muted-foreground" /></div>
      ) : !conversationId ? (
        <p className="text-sm text-muted-foreground">Este contato ainda não tem conversa no WhatsApp.</p>
      ) : isLoading ? (
        <div className="flex justify-center py-6"><Loader2 className="w-5 h-5 animate-spin text-muted-foreground" /></div>
      ) : (
        <div className="space-y-2 max-h-[60vh] overflow-y-auto pr-1">
          {hasNextPage && (
            <Button variant="ghost" size="sm" className="w-full text-xs" onClick={() => fetchNextPage()} disabled={isFetchingNextPage}>
              {isFetchingNextPage ? <Loader2 className="w-4 h-4 animate-spin" /> : "Mensagens anteriores"}
            </Button>
          )}
          {messages.length === 0 && <p className="text-sm text-muted-foreground">Nenhuma mensagem.</p>}
          {messages.map((m) => (
            <div key={m.id} className={cn("flex", m.direction === "INCOMING" ? "justify-start" : "justify-end")}>
              <div className={cn("max-w-[85%] rounded-xl px-3 py-2 text-sm",
                m.direction === "INCOMING" ? "bg-muted" : m.direction === "INTERNAL" ? "bg-amber-500/10 border border-amber-500/30" : "bg-primary/10")}>
                {m.direction === "INTERNAL" && <span className="block text-[11px] font-semibold text-amber-700 dark:text-amber-400">Nota interna{m.author_name ? ` · ${m.author_name}` : ""}</span>}
                <p className="whitespace-pre-wrap break-words">{m.content || (m.message_type !== "text" ? `[${m.message_type}]` : "")}</p>
                <span className="block text-[10px] text-muted-foreground text-right mt-0.5">{formatDateTime(m.created_at)}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

export default function FunilLead() {
  const { id = null } = useParams();
  const navigate = useNavigate();
  const { data: lead, isLoading, isError } = useLead(id);
  const actions = useLeadActions(id);
  const [lostOpen, setLostOpen] = useState(false);
  const [callOpen, setCallOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [nextStep, setNextStep] = useState("");
  const [nextAt, setNextAt] = useState("");

  useEffect(() => {
    setNextStep(lead?.next_step || "");
    setNextAt(toLocalInput(lead?.next_action_at));
  }, [lead?.id, lead?.next_step, lead?.next_action_at]);

  const back = () => (window.history.length > 1 ? navigate(-1) : navigate("/funil"));
  const changeStage = (stage: LeadStage) => {
    if (stage === "LOST") setLostOpen(true);
    else actions.changeStage({ stage }).catch(() => undefined);
  };

  if (isLoading || !lead) {
    return (
      <PageShell title="Lead">
        <div className="flex flex-col items-center gap-3 py-20 text-muted-foreground">
          {isError ? (
            <>
              <p className="text-sm">Lead não encontrado.</p>
              <Button variant="outline" onClick={() => navigate("/funil")}>Voltar ao funil</Button>
            </>
          ) : <Loader2 className="w-6 h-6 animate-spin" />}
        </div>
      </PageShell>
    );
  }

  const qualificationEntries = Object.entries(lead.qualification || {})
    .filter(([key, value]) => !MIRRORED_FIELDS.has(key) && value !== null && value !== "");
  const value = lead.contract_value || lead.quoted_amount || 0;
  const lost = lead.customer_state_now === "LOST";
  const won = lead.customer_state_now === "CONTRACT_SIGNED";

  return (
    <PageShell title="Funil de vendas" maxWidthClassName="max-w-[1400px]">
      {/* Cabeçalho */}
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="flex items-start gap-2 min-w-0">
          <Button variant="ghost" size="icon" className="shrink-0" onClick={back} title="Voltar ao funil" aria-label="Voltar ao funil">
            <ArrowLeft className="w-5 h-5" />
          </Button>
          <div className="min-w-0">
            <h2 className="text-xl sm:text-2xl font-bold text-foreground truncate">{lead.name || "Sem nome"}</h2>
            <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground mt-1">
              {lead.company && <span>{lead.company}</span>}
              <Badge variant="outline" className={LEAD_STATUS_STYLES[lead.customer_state_now]}>{LEAD_STATUS_LABELS[lead.customer_state_now]}</Badge>
              {lead.product && <Badge variant="secondary">{PRODUCT_LABELS[lead.product]}</Badge>}
              {lead.ai_qualified_at && (
                <Badge variant="outline" className="border-emerald-500/40 text-emerald-700 dark:text-emerald-400">
                  <BadgeCheck className="w-3 h-3 mr-1" /> Qualificado IA
                </Badge>
              )}
              {lead.human_operator && <Badge variant="destructive">Operador humano</Badge>}
            </div>
          </div>
        </div>
        <div className="flex flex-wrap gap-2 lg:justify-end">
          <Button variant="outline" onClick={() => setEditOpen(true)}><Pencil className="w-4 h-4 mr-1.5" /> Editar</Button>
          <Button variant="outline" onClick={() => navigate(`/calculadora?lead=${lead.id}`)}><Calculator className="w-4 h-4 mr-1.5" /> Calculadora</Button>
          <Button variant="outline" onClick={() => navigate(`/agenda?lead=${lead.id}`)}><CalendarPlus className="w-4 h-4 mr-1.5" /> Agendar</Button>
          <Button variant="outline" onClick={() => setCallOpen(true)}><PhoneCall className="w-4 h-4 mr-1.5" /> Ligação</Button>
          <Button className="bg-emerald-600 hover:bg-emerald-700 text-white" disabled={won}
            onClick={() => actions.changeStage({ stage: "CONTRACT_SIGNED" }).catch(() => undefined)}>
            <Trophy className="w-4 h-4 mr-1.5" /> Ganho
          </Button>
          <Button variant="outline" className="text-rose-600 border-rose-500/40" disabled={lost} onClick={() => setLostOpen(true)}>
            <XCircle className="w-4 h-4 mr-1.5" /> Perdido
          </Button>
        </div>
      </div>

      <StageStepper stage={lead.customer_state_now} onChange={changeStage} />
      {lost && (
        <p className="rounded-xl border border-rose-500/30 bg-rose-500/5 px-4 py-2 text-sm text-rose-600">
          Lead perdido{lead.lost_reason ? `: ${LOST_REASON_LABELS[lead.lost_reason] || lead.lost_reason}` : ""}. Clique numa etapa para reabrir.
        </p>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-[340px_minmax(0,1fr)] gap-4 items-start">
        {/* Coluna da esquerda */}
        <div className="space-y-4">
          <Card title="Negócio">
            <dl className="space-y-1.5">
              <Field label="Valor">{value > 0 ? <span className="font-semibold">{formatBRL(value)}</span> : null}</Field>
              <Field label="Produto">{lead.product ? PRODUCT_LABELS[lead.product] : null}</Field>
              <Field label="Origem">{lead.origin ? ORIGIN_LABELS[lead.origin] || lead.origin : null}</Field>
              <Field label="Responsável">{OWNER_LABELS[lead.owner || "sdr"]}</Field>
              <Field label="Data do evento">{lead.event_date ? formatDay(lead.event_date) : null}</Field>
              <Field label="Público">{lead.guest_count ? `${lead.guest_count} pessoas` : null}</Field>
              <Field label="Local">{lead.venue}</Field>
            </dl>
          </Card>

          <Card title="Contato" action={(
            <button className="flex items-center gap-1 text-xs text-muted-foreground hover:underline" onClick={() => navigate(`/contatos?contato=${lead.id}`)}>
              <Contact className="w-3.5 h-3.5" /> Leads anteriores
            </button>
          )}>
            <dl className="space-y-1.5">
              <Field label="Telefone">
                <a href={`tel:+${lead.phone}`} className="inline-flex items-center gap-1 hover:underline"><Phone className="w-3.5 h-3.5" /> {phoneDisplay(lead.phone)}</a>
              </Field>
              <Field label="E-mail">{lead.email}</Field>
              <Field label="Empresa">{lead.company}</Field>
              <Field label="Cargo">{lead.role}</Field>
            </dl>
          </Card>

          <Card title="Qualificação">
            {qualificationEntries.length === 0 ? (
              <p className="text-sm text-muted-foreground">Nenhum dado coletado ainda.</p>
            ) : (
              <dl className="space-y-1.5">
                {qualificationEntries.map(([key, v]) => <Field key={key} label={key.replace(/_/g, " ")}>{String(v)}</Field>)}
              </dl>
            )}
            {lead.pending_fields.length > 0 && (
              <div className="flex flex-wrap gap-1.5 pt-1">
                <span className="text-xs text-muted-foreground">Pendências:</span>
                {lead.pending_fields.map((field) => (
                  <span key={field} className="text-xs px-2 py-0.5 rounded bg-rose-500/10 text-rose-600">{field.replace(/_/g, " ")}</span>
                ))}
              </div>
            )}
          </Card>

          <Card title="Sinalizações">
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(FLAG_LABELS).map(([flag, label]) => {
                const active = lead.flags.includes(flag);
                return (
                  <button key={flag}
                    onClick={() => actions.setFlags(active ? { remove: [flag] } : { add: [flag] }).catch(() => undefined)}
                    className={cn("text-xs px-2.5 py-1 rounded-full border transition-colors",
                      active ? "bg-amber-500 text-white border-amber-500" : "border-border text-muted-foreground hover:bg-secondary")}>
                    {label}
                  </button>
                );
              })}
            </div>
          </Card>

          <Card title="Próxima ação">
            <Input value={nextStep} onChange={(e) => setNextStep(e.target.value)} placeholder="Ex.: ligar para fechar" />
            <div className="flex gap-2">
              <Input type="datetime-local" value={nextAt} onChange={(e) => setNextAt(e.target.value)} />
              <Button size="sm" className="shrink-0 h-10"
                onClick={() => actions.setNextAction({ next_step: nextStep, next_action_at: nextAt ? new Date(nextAt).toISOString() : null }).catch(() => undefined)}>
                Salvar
              </Button>
            </div>
          </Card>
        </div>

        {/* Área principal */}
        <Tabs defaultValue="atividades" className="min-w-0">
          <TabsList className="w-full justify-start overflow-x-auto">
            <TabsTrigger value="atividades">Atividades</TabsTrigger>
            <TabsTrigger value="propostas">Propostas</TabsTrigger>
            <TabsTrigger value="whatsapp">WhatsApp</TabsTrigger>
            <TabsTrigger value="anexos">Anexos{lead.attachments.length ? ` (${lead.attachments.length})` : ""}</TabsTrigger>
          </TabsList>
          <TabsContent value="atividades"><ActivitiesTab leadId={lead.id} /></TabsContent>
          <TabsContent value="propostas"><ProposalsTab lead={lead} /></TabsContent>
          <TabsContent value="whatsapp"><WhatsAppTab lead={lead} /></TabsContent>
          <TabsContent value="anexos">
            <Card title="Anexos">
              {lead.attachments.length === 0 ? (
                <p className="text-sm text-muted-foreground">Nenhum anexo. Arquivos que o cliente manda (projeto, orçamento) aparecem aqui.</p>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
                  {lead.attachments.map((attachment) => <AttachmentView key={attachment.url} attachment={attachment} />)}
                </div>
              )}
            </Card>
          </TabsContent>
        </Tabs>
      </div>

      <EditLeadDialog lead={lead} open={editOpen} onClose={() => setEditOpen(false)} />
      <LostReasonDialog open={lostOpen} onClose={() => setLostOpen(false)}
        onConfirm={(reason) => {
          setLostOpen(false);
          actions.changeStage({ stage: "LOST", lost_reason: reason }).catch(() => undefined);
        }} />
      <CallDialog open={callOpen} onClose={() => setCallOpen(false)}
        onConfirm={(outcome, notes) => {
          setCallOpen(false);
          actions.logCall({ outcome, notes }).catch(() => undefined);
        }} />
    </PageShell>
  );
}
