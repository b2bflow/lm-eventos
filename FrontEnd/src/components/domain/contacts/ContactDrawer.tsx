import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { History, Loader2, MessageSquare, Phone, Plus, SquareKanban } from "lucide-react";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import {
  CONTACT_TYPE_LABELS, LEAD_STATUS_LABELS, LEAD_STATUS_STYLES, LOST_REASON_LABELS, ORIGIN_LABELS, OWNER_LABELS,
  PRODUCT_LABELS, PROPOSAL_MODE_LABELS,
} from "@/constants/mappings";
import { formatBRL, formatDateTime, formatDay, phoneDisplay } from "@/lib/format";
import {
  useContact, useContactActions, useContactLeadTimeline, type ContactDetail, type ContactLead,
} from "@/hooks/useContacts";
import { AttachmentView } from "@/components/domain/funnel/AttachmentView";

const NONE = "__none__";

type ContactForm = {
  name: string; email: string; company: string; role: string; contact_type: string; origin: string; owner: string; notes: string;
};

function toForm(contact: ContactDetail): ContactForm {
  return {
    name: contact.name || "", email: contact.email || "", company: contact.company || "", role: contact.role || "",
    contact_type: contact.contact_type || "lead", origin: contact.origin || "", owner: contact.owner || "sdr",
    notes: contact.notes || "",
  };
}

function Section({ title, children, action }: { title: string; children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <section className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">{title}</h3>
        {action}
      </div>
      {children}
    </section>
  );
}

function LeadHistoryItem({ contactId, lead }: { contactId: string; lead: ContactLead }) {
  const [showTimeline, setShowTimeline] = useState(false);
  const { data: timeline = [], isLoading } = useContactLeadTimeline(showTimeline ? contactId : null, lead.id);
  const value = lead.contract_value || lead.quoted_amount;
  return (
    <li className={cn("rounded-lg border p-3 space-y-2 text-sm", lead.current && "border-primary/50")}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold">Lead {lead.number}</span>
        {lead.current && <Badge>Atual</Badge>}
        <Badge variant="outline" className={LEAD_STATUS_STYLES[lead.stage]}>{LEAD_STATUS_LABELS[lead.stage] || lead.stage}</Badge>
        {lead.product && <Badge variant="secondary">{PRODUCT_LABELS[lead.product] || lead.product}</Badge>}
      </div>
      <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
        <dt className="text-muted-foreground">Início</dt><dd>{formatDay(lead.started_at)}</dd>
        {lead.closed_at && (<><dt className="text-muted-foreground">Encerrado</dt><dd>{formatDay(lead.closed_at)}</dd></>)}
        {lead.event_date && (<><dt className="text-muted-foreground">Evento</dt><dd>{formatDay(lead.event_date)}</dd></>)}
        {!!value && (<><dt className="text-muted-foreground">{lead.contract_value ? "Contrato" : "Proposta"}</dt><dd>{formatBRL(value)}</dd></>)}
        {lead.lost_reason && (<><dt className="text-muted-foreground">Motivo da perda</dt><dd>{LOST_REASON_LABELS[lead.lost_reason]}</dd></>)}
      </dl>
      {lead.proposals.length > 0 && (
        <ul className="space-y-1">
          {lead.proposals.map((p) => (
            <li key={p.id} className="flex items-center justify-between gap-2 text-xs rounded bg-secondary/50 px-2 py-1">
              <span>v{p.version} · {PROPOSAL_MODE_LABELS[p.mode] || p.mode} · {p.status_label}</span>
              <span className="font-semibold">{formatBRL(p.total)}</span>
            </li>
          ))}
        </ul>
      )}
      <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={() => setShowTimeline(!showTimeline)}>
        <History className="w-3.5 h-3.5 mr-1" /> {showTimeline ? "Esconder linha do tempo" : "Linha do tempo"}
      </Button>
      {showTimeline && (isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : (
        <ol className="space-y-1.5 border-l pl-3 max-h-60 overflow-y-auto">
          {timeline.length === 0 && <li className="text-xs text-muted-foreground">Sem registros.</li>}
          {timeline.map((entry) => (
            <li key={entry.id} className="text-xs">
              <span className="text-muted-foreground">{formatDateTime(entry.created_at)}</span>
              <p className="whitespace-pre-wrap break-words">{entry.description}</p>
            </li>
          ))}
        </ol>
      ))}
    </li>
  );
}

export function ContactDrawer({ contactId, onClose }: { contactId: string | null; onClose: () => void }) {
  const navigate = useNavigate();
  const { data: contact, isLoading } = useContact(contactId);
  const { update, newLead } = useContactActions(contactId);
  const [form, setForm] = useState<ContactForm | null>(null);
  const [product, setProduct] = useState("");

  useEffect(() => {
    if (contact) setForm(toForm(contact));
  }, [contact]);

  const dirty = contact && form ? JSON.stringify(form) !== JSON.stringify(toForm(contact)) : false;
  const currentLead = contact?.leads.find((lead) => lead.current);
  const canOpenLead = !!contact && !contact.current_lead_open && !contact.human_operator;

  const save = () => {
    if (!contact || !form) return;
    const original = toForm(contact);
    const changes = Object.fromEntries(
      Object.entries(form).filter(([key, value]) => value !== original[key as keyof ContactForm])
        .map(([key, value]) => [key, value || null]),
    );
    update.mutate(changes);
  };

  const input = (key: keyof ContactForm, label: string, type = "text") => form && (
    <div className="space-y-1">
      <Label htmlFor={`contact-${key}`}>{label}</Label>
      <Input id={`contact-${key}`} type={type} value={form[key]} onChange={(e) => setForm({ ...form, [key]: e.target.value })} />
    </div>
  );

  const select = (key: keyof ContactForm, label: string, options: Record<string, string>, allowEmpty = false) => form && (
    <div className="space-y-1">
      <Label>{label}</Label>
      <Select value={form[key] || NONE} onValueChange={(v) => setForm({ ...form, [key]: v === NONE ? "" : v })}>
        <SelectTrigger><SelectValue /></SelectTrigger>
        <SelectContent>
          {allowEmpty && <SelectItem value={NONE}>Não informada</SelectItem>}
          {Object.entries(options).map(([k, l]) => <SelectItem key={k} value={k}>{l}</SelectItem>)}
        </SelectContent>
      </Select>
    </div>
  );

  return (
    <Sheet open={!!contactId} onOpenChange={(open) => !open && onClose()}>
      <SheetContent side="right" className="w-full sm:max-w-xl overflow-y-auto p-0">
        {isLoading || !contact || !form ? (
          <div className="flex justify-center py-20"><Loader2 className="w-6 h-6 animate-spin" /></div>
        ) : (
          <div className="p-5 space-y-6">
            <SheetHeader className="text-left space-y-2">
              <SheetTitle className="pr-6">{contact.name || "Sem nome"}</SheetTitle>
              <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
                <a href={`tel:+${contact.phone}`} className="flex items-center gap-1 hover:underline">
                  <Phone className="w-3.5 h-3.5" /> {phoneDisplay(contact.phone)}
                </a>
                <Badge variant="outline">{CONTACT_TYPE_LABELS[contact.contact_type] || contact.contact_type}</Badge>
                <Badge variant="outline">{OWNER_LABELS[contact.owner] || contact.owner}</Badge>
                {contact.human_operator && <Badge variant="destructive">Parceiro / operador humano</Badge>}
              </div>
            </SheetHeader>

            <div className="grid grid-cols-2 gap-2">
              <Button size="sm" variant="outline" disabled={!currentLead} onClick={() => navigate(`/funil?lead=${contact.id}`)}>
                <SquareKanban className="w-4 h-4 mr-1" /> Abrir no funil
              </Button>
              <Button size="sm" variant="outline" disabled={!contact.conversation_id}
                onClick={() => navigate(`/whatsapp?conversa=${contact.conversation_id}`)}>
                <MessageSquare className="w-4 h-4 mr-1" /> Conversa
              </Button>
            </div>

            <Section title={`Leads (${contact.leads.length})`}>
              {contact.leads.length === 0 ? (
                <p className="text-sm text-muted-foreground">Nenhum lead deste contato.</p>
              ) : (
                <ul className="space-y-2">
                  {contact.leads.map((lead) => <LeadHistoryItem key={lead.id} contactId={contact.id} lead={lead} />)}
                </ul>
              )}
            </Section>

            <Section title="Novo lead">
              {canOpenLead ? (
                <div className="flex flex-col sm:flex-row gap-2">
                  <Select value={product} onValueChange={setProduct}>
                    <SelectTrigger className="sm:flex-1"><SelectValue placeholder="Produto do novo lead" /></SelectTrigger>
                    <SelectContent>
                      {Object.entries(PRODUCT_LABELS).map(([k, l]) => <SelectItem key={k} value={k}>{l}</SelectItem>)}
                    </SelectContent>
                  </Select>
                  <Button size="sm" className="shrink-0" disabled={!product || newLead.isPending}
                    onClick={() => newLead.mutate(product, { onSuccess: () => setProduct("") })}>
                    <Plus className="w-4 h-4 mr-1" /> Abrir lead
                  </Button>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">
                  {contact.human_operator
                    ? "Parceiro fica com a Erica e não entra no funil. Desmarque 'Parceiro' para abrir um lead."
                    : "Já existe um lead em andamento. Um novo lead pode ser aberto quando ele for fechado (contrato assinado ou perdido)."}
                </p>
              )}
            </Section>

            <Section title="Dados do contato">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {input("name", "Nome")}
                {input("company", "Empresa")}
                {input("role", "Cargo")}
                {input("email", "E-mail", "email")}
                {select("contact_type", "Tipo", CONTACT_TYPE_LABELS)}
                {select("origin", "Origem", ORIGIN_LABELS, true)}
                {select("owner", "Responsável", OWNER_LABELS)}
                <div className="flex items-center gap-2 sm:pt-6">
                  <Switch
                    id="contact-partner"
                    checked={contact.human_operator}
                    disabled={update.isPending}
                    onCheckedChange={(value) => update.mutate({ human_operator: value })}
                  />
                  <Label htmlFor="contact-partner">Parceiro (fica com a Erica)</Label>
                </div>
              </div>
              <div className="space-y-1">
                <Label htmlFor="contact-notes">Observações</Label>
                <Textarea id="contact-notes" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
              </div>
              <Button size="sm" disabled={!dirty || update.isPending} onClick={save}>Salvar contato</Button>
            </Section>

            {contact.attachments.length > 0 && (
              <Section title={`Anexos (${contact.attachments.length})`}>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {contact.attachments.map((attachment, index) => (
                    <div key={`${attachment.url}-${index}`} className="space-y-1">
                      <AttachmentView attachment={attachment} />
                      <span className="text-[11px] text-muted-foreground">Lead {attachment.lead_number}</span>
                    </div>
                  ))}
                </div>
              </Section>
            )}
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
