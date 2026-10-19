import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Calculator, CalendarPlus, CheckCircle2, Contact, FileText, Loader2, MessageSquare, Phone, PhoneCall, Send, ThumbsDown,
  ThumbsUp, XCircle,
} from "lucide-react";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { safeMediaUrl } from "@/lib/safeUrl";
import {
  FLAG_LABELS, LEAD_STATUS_LABELS, LEAD_STATUS_OPTIONS, LEAD_STATUS_STYLES, LOST_REASON_LABELS, OWNER_LABELS,
  PRODUCT_LABELS, PROPOSAL_MODE_LABELS, type LeadStage,
} from "@/constants/mappings";
import { openProposalPdf } from "@/hooks/useSales";
import { toast } from "sonner";
import { formatBRL, formatDateTime, formatDay, isOverdue, phoneDisplay, utcIso } from "@/lib/format";
import {
  isAdminUser, useCurrentUser, useLead, useLeadActions, useLeadTasks, useProposals, useTimeline, type Attachment,
} from "@/hooks/useFunnel";
import { CallDialog, LostReasonDialog } from "./LeadDialogs";

interface LeadDrawerProps {
  leadId: string | null;
  onClose: () => void;
}

const IMAGE_RE = /[./](png|jpe?g|gif|webp)($|\?)/i;
const isImage = (a: Attachment) => IMAGE_RE.test(a.url) || IMAGE_RE.test(a.name || "");
const isPdf = (a: Attachment) => /\.pdf($|\?)/i.test(a.url) || /\.pdf$/i.test(a.name || "");

// Campos da qualificação já exibidos pelos campos do CRM (espelhados no backend)
const MIRRORED_FIELDS = new Set(["nome", "email", "empresa", "cargo", "local", "data_evento", "publico"]);

function toLocalInput(value?: string | null): string {
  if (!value) return "";
  const d = new Date(utcIso(value));
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function AttachmentView({ attachment }: { attachment: Attachment }) {
  const url = safeMediaUrl(attachment.url);
  if (!url) {
    return <p className="text-xs text-muted-foreground">{attachment.name} (endereço inválido)</p>;
  }
  if (isImage(attachment)) {
    return (
      <a href={url} target="_blank" rel="noreferrer" className="block">
        <img src={url} alt={attachment.name} className="rounded-lg max-h-48 w-full object-cover bg-muted" loading="lazy" />
        <span className="text-[11px] text-muted-foreground">{attachment.name}</span>
      </a>
    );
  }
  return (
    <div className="space-y-1">
      {isPdf(attachment) && (
        <iframe src={url} title={attachment.name} className="w-full h-56 rounded-lg bg-white hidden sm:block" />
      )}
      <a href={url} target="_blank" rel="noreferrer" className="flex items-center gap-2 text-xs underline">
        <FileText className="w-4 h-4" /> {attachment.name}
      </a>
    </div>
  );
}

function Section({ title, children, className }: { title: string; children: React.ReactNode; className?: string }) {
  return (
    <section className={cn("space-y-2", className)}>
      <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">{title}</h3>
      {children}
    </section>
  );
}

export function LeadDrawer({ leadId, onClose }: LeadDrawerProps) {
  const navigate = useNavigate();
  const { data: lead, isLoading } = useLead(leadId);
  const { data: timeline = [] } = useTimeline(leadId);
  const { data: tasks = [] } = useLeadTasks(leadId);
  const { data: proposals = [] } = useProposals(leadId);
  const { data: me } = useCurrentUser();
  const actions = useLeadActions(leadId);
  const isAdmin = isAdminUser(me);

  const [lostOpen, setLostOpen] = useState(false);
  const [callOpen, setCallOpen] = useState(false);
  const [note, setNote] = useState("");
  const [nextStep, setNextStep] = useState("");
  const [nextAt, setNextAt] = useState("");

  useEffect(() => {
    setNextStep(lead?.next_step || "");
    setNextAt(toLocalInput(lead?.next_action_at));
  }, [lead?.id, lead?.next_step, lead?.next_action_at]);

  const qualificationEntries = Object.entries(lead?.qualification || {}).filter(([key]) => !MIRRORED_FIELDS.has(key));

  return (
    <Sheet open={!!leadId} onOpenChange={(open) => !open && onClose()}>
      <SheetContent side="right" className="w-full sm:max-w-xl overflow-y-auto p-0">
        {isLoading || !lead ? (
          <div className="flex justify-center py-20"><Loader2 className="w-6 h-6 animate-spin" /></div>
        ) : (
          <div className="p-5 space-y-6">
            <SheetHeader className="text-left space-y-2">
              <SheetTitle className="pr-6">{lead.name || "Sem nome"}</SheetTitle>
              <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
                <a href={`tel:+${lead.phone}`} className="flex items-center gap-1 hover:underline">
                  <Phone className="w-3.5 h-3.5" /> {phoneDisplay(lead.phone)}
                </a>
                <Badge variant="outline" className={LEAD_STATUS_STYLES[lead.customer_state_now]}>
                  {LEAD_STATUS_LABELS[lead.customer_state_now]}
                </Badge>
                {lead.product && <Badge variant="secondary">{PRODUCT_LABELS[lead.product]}</Badge>}
                <Badge variant="outline">{OWNER_LABELS[lead.owner || "sdr"]}</Badge>
                {lead.human_operator && <Badge variant="destructive">Operador humano</Badge>}
                <button className="flex items-center gap-1 text-xs hover:underline" onClick={() => navigate(`/contatos?contato=${lead.id}`)}>
                  <Contact className="w-3.5 h-3.5" /> Ver contato e leads anteriores
                </button>
              </div>
              {lead.customer_state_now === "LOST" && lead.lost_reason && (
                <p className="text-sm text-rose-600">Perdido: {LOST_REASON_LABELS[lead.lost_reason]}</p>
              )}
            </SheetHeader>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              <Button size="sm" onClick={() => navigate(`/calculadora?lead=${lead.id}`)}>
                <Calculator className="w-4 h-4 mr-1" /> Calculadora
              </Button>
              <Button size="sm" variant="outline" onClick={() => navigate(`/agenda?lead=${lead.id}`)}>
                <CalendarPlus className="w-4 h-4 mr-1" /> Agendar
              </Button>
              <Button size="sm" variant="outline" onClick={() => setCallOpen(true)}>
                <PhoneCall className="w-4 h-4 mr-1" /> Ligação
              </Button>
              <Button size="sm" variant="outline" className="text-rose-600" onClick={() => setLostOpen(true)}
                disabled={lead.customer_state_now === "LOST"}>
                <XCircle className="w-4 h-4 mr-1" /> Perdido
              </Button>
            </div>

            <Section title="Etapa">
              <Select
                value={lead.customer_state_now}
                onValueChange={(value) => {
                  if (value === "LOST") setLostOpen(true);
                  else actions.changeStage({ stage: value as LeadStage }).catch(() => undefined);
                }}
              >
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {LEAD_STATUS_OPTIONS.map((stage) => (
                    <SelectItem key={stage} value={stage}>{LEAD_STATUS_LABELS[stage]}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Section>

            <Section title="Sinalizações">
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(FLAG_LABELS).map(([flag, label]) => {
                  const active = lead.flags.includes(flag);
                  return (
                    <button
                      key={flag}
                      onClick={() => actions.setFlags(active ? { remove: [flag] } : { add: [flag] }).catch(() => undefined)}
                      className={cn(
                        "text-xs px-2.5 py-1 rounded-full border transition-colors",
                        active ? "bg-amber-500 text-white border-amber-500" : "border-border text-muted-foreground hover:bg-secondary"
                      )}
                    >
                      {label}
                    </button>
                  );
                })}
              </div>
            </Section>

            <Section title="Próxima ação">
              <div className="flex flex-col sm:flex-row gap-2">
                <Input value={nextStep} onChange={(e) => setNextStep(e.target.value)} placeholder="Ex.: ligar para fechar" />
                <Input type="datetime-local" value={nextAt} onChange={(e) => setNextAt(e.target.value)} className="sm:w-56" />
                <Button
                  size="sm"
                  className="shrink-0"
                  onClick={() =>
                    actions.setNextAction({ next_step: nextStep, next_action_at: nextAt ? new Date(nextAt).toISOString() : null })
                      .catch(() => undefined)
                  }
                >
                  Salvar
                </Button>
              </div>
            </Section>

            {tasks.length > 0 && (
              <Section title="Tarefas">
                <ul className="space-y-1.5">
                  {tasks.map((task) => (
                    <li key={task.id} className="flex items-center justify-between gap-2 text-sm rounded-lg border px-3 py-2">
                      <span>
                        {task.label}{" "}
                        <span className={cn("text-xs", isOverdue(task.due_at) ? "text-rose-600 font-semibold" : "text-muted-foreground")}>
                          até {formatDateTime(task.due_at)}
                        </span>
                      </span>
                      <Button size="sm" variant="ghost" onClick={() => actions.completeTask(task.id).catch(() => undefined)}>
                        <CheckCircle2 className="w-4 h-4" />
                      </Button>
                    </li>
                  ))}
                </ul>
              </Section>
            )}

            <Section title="Qualificação">
              <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1.5 text-sm">
                {lead.event_date && (<><dt className="text-muted-foreground">Data do evento</dt><dd>{formatDay(lead.event_date)}</dd></>)}
                {!!lead.guest_count && (<><dt className="text-muted-foreground">Público</dt><dd>{lead.guest_count}</dd></>)}
                {lead.venue && (<><dt className="text-muted-foreground">Local</dt><dd>{lead.venue}</dd></>)}
                {lead.company && (<><dt className="text-muted-foreground">Empresa</dt><dd>{lead.company}</dd></>)}
                {qualificationEntries
                  .filter(([, value]) => value !== null && value !== "")
                  .map(([key, value]) => (
                    <div key={key} className="contents">
                      <dt className="text-muted-foreground">{key.replace(/_/g, " ")}</dt>
                      <dd className="break-words">{String(value)}</dd>
                    </div>
                  ))}
              </dl>
              {qualificationEntries.length === 0 && !lead.event_date && (
                <p className="text-sm text-muted-foreground">Nenhum dado coletado ainda.</p>
              )}
              {lead.pending_fields.length > 0 && (
                <div className="flex flex-wrap gap-1.5 pt-1">
                  <span className="text-xs text-muted-foreground">Pendências:</span>
                  {lead.pending_fields.map((field) => (
                    <span key={field} className="text-xs px-2 py-0.5 rounded bg-rose-500/10 text-rose-600">{field.replace(/_/g, " ")}</span>
                  ))}
                </div>
              )}
            </Section>

            {lead.attachments.length > 0 && (
              <Section title="Anexos">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {lead.attachments.map((attachment) => (
                    <AttachmentView key={attachment.url} attachment={attachment} />
                  ))}
                </div>
              </Section>
            )}

            <Section title="Propostas">
              {proposals.length === 0 ? (
                <p className="text-sm text-muted-foreground">Nenhuma proposta ainda.</p>
              ) : (
                <ul className="space-y-2">
                  {proposals.map((p) => (
                    <li key={p.id} className="rounded-lg border p-3 space-y-2">
                      <div className="flex items-center justify-between gap-2 text-sm">
                        <span className="font-semibold">v{p.version} · {PROPOSAL_MODE_LABELS[p.mode] || p.mode}</span>
                        <span className="font-bold">{formatBRL(p.total)}</span>
                      </div>
                      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                        <Badge variant={p.status === "aguardando_aprovacao" ? "destructive" : "secondary"}>{p.status_label}</Badge>
                        {p.valid_until && <span>Válida até {formatDateTime(p.valid_until)}</span>}
                      </div>
                      {p.lock_reasons.length > 0 && (
                        <ul className="text-xs text-rose-600 list-disc pl-4">
                          {p.lock_reasons.map((r, i) => <li key={i}>{r.message}{r.detail ? `: ${r.detail}` : ""}</li>)}
                        </ul>
                      )}
                      <div className="flex flex-wrap gap-2">
                        <Button size="sm" variant="ghost" onClick={() => navigate(`/calculadora?lead=${lead.id}&proposal=${p.id}`)}>
                          Abrir
                        </Button>
                        <Button size="sm" variant="ghost"
                          onClick={() => openProposalPdf(p.id).catch(() => toast.error("Não foi possível gerar o PDF."))}>
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
                            <Button size="sm" disabled={actions.isPending}
                              onClick={() => actions.sendProposalWhatsApp(p.id).catch(() => undefined)}>
                              <Send className="w-4 h-4 mr-1" /> Enviar no WhatsApp
                            </Button>
                            <Button size="sm" variant="outline" onClick={() => actions.proposalAction(p.id, "send").catch(() => undefined)}>
                              Marcar enviada
                            </Button>
                          </>
                        )}
                        {p.status === "enviada" && (
                          <>
                            <Button size="sm" onClick={() => actions.proposalAction(p.id, "accept").catch(() => undefined)}>
                              <CheckCircle2 className="w-4 h-4 mr-1" /> Aceita
                            </Button>
                            <Button size="sm" variant="outline" onClick={() => actions.proposalAction(p.id, "reject").catch(() => undefined)}>
                              Recusada
                            </Button>
                          </>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </Section>

            <Section title="Nota interna">
              <Textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="Visível só para a equipe" />
              <Button
                size="sm"
                disabled={!note.trim()}
                onClick={() => actions.addNote(note).then(() => setNote("")).catch(() => undefined)}
              >
                <MessageSquare className="w-4 h-4 mr-1" /> Adicionar nota
              </Button>
            </Section>

            <Section title="Linha do tempo">
              <ol className="space-y-2 border-l pl-4">
                {timeline.map((entry) => (
                  <li key={entry.id} className="text-sm">
                    <span className="text-xs text-muted-foreground">{formatDateTime(entry.created_at)}</span>
                    <p className="whitespace-pre-wrap break-words">{entry.description}</p>
                  </li>
                ))}
              </ol>
            </Section>
          </div>
        )}

        <LostReasonDialog
          open={lostOpen}
          onClose={() => setLostOpen(false)}
          onConfirm={(reason) => {
            setLostOpen(false);
            actions.changeStage({ stage: "LOST", lost_reason: reason }).catch(() => undefined);
          }}
        />
        <CallDialog
          open={callOpen}
          onClose={() => setCallOpen(false)}
          onConfirm={(outcome, notes) => {
            setCallOpen(false);
            actions.logCall({ outcome, notes }).catch(() => undefined);
          }}
        />
      </SheetContent>
    </Sheet>
  );
}
