import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { addDays, addMinutes, addMonths, differenceInCalendarDays, format, isSameDay, isSameMonth, startOfDay, startOfMonth, startOfWeek } from "date-fns";
import { ptBR } from "date-fns/locale";
import { toast } from "sonner";
import {
  AlignLeft, CalendarPlus, ChevronLeft, ChevronRight, Clock, Link2, Loader2, MapPin, MessageCircle, Pencil, Plus,
  RefreshCw, Repeat, SquareKanban, Trash2, UserRound, Video, X, type LucideIcon,
} from "lucide-react";
import { PageShell } from "@/components/shared/PageShell";
import { FilterBar, Legend } from "@/components/shared/FilterBar";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import api from "@/services/api";
import { cn } from "@/lib/utils";
import { phoneDisplay, utcIso } from "@/lib/format";
import { TONE_DOT_CLASSES, type Tone } from "@/lib/tones";
import { isAdminUser, useCurrentUser, useLead } from "@/hooks/useFunnel";
import { ContactPicker } from "@/components/domain/contacts/ContactPicker";
import { DateField, RecurrenceSelect, ScopeDialog, TimeSelect, type Scope } from "@/components/domain/agenda/EventFormParts";
import { dayToDate, describeRule, followStart, sameRule, type RecurrenceRule } from "@/components/domain/agenda/recurrence";

type PickedContact = { id: string; name?: string | null; phone?: string };

interface AgendaEvent {
  id: string;
  type: string;
  type_label: string;
  title: string;
  customer_id?: string | null;
  customer_name?: string | null;
  start: string;
  end: string;
  all_day?: boolean;
  series_id?: string | null;
  recurrence?: RecurrenceRule | null;
  location?: string | null;
  meet_link?: string | null;
  notes?: string | null;
  source: string;
  sync_status?: string;
}

const SYNC_LABELS: Record<string, string> = {
  sincronizado: "Sincronizado",
  pendente: "Pendente",
  erro: "Falhou (ficou só na plataforma)",
  local: "Só na plataforma",
};

interface GoogleStatus {
  client_configured: boolean;
  authorized: boolean;
  connected: boolean;
  redirect_uri: string;
}

type View = "day" | "week" | "month" | "list";

const TYPE_TONES: Record<string, Tone> = {
  reuniao_online: "info",
  visita_tecnica: "ai",
  evento_confirmado: "success",
  bloqueio: "neutral",
  externo: "warning",
};

const TYPE_LEGEND: { type: string; label: string }[] = [
  { type: "reuniao_online", label: "Reunião online" },
  { type: "visita_tecnica", label: "Visita técnica" },
  { type: "evento_confirmado", label: "Evento confirmado" },
  { type: "bloqueio", label: "Bloqueio" },
  { type: "externo", label: "Google (externo)" },
];

// Tipos que dá para criar (as abas "Evento | Tarefa" do Google, aqui com os tipos da LM).
const TYPE_CHIPS: [string, string][] = [
  ["reuniao_online", "Reunião online"],
  ["visita_tecnica", "Visita técnica"],
  ["evento_confirmado", "Evento confirmado"],
  ["bloqueio", "Bloqueio"],
];

const WEEKDAYS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"];
const HOURS = Array.from({ length: 15 }, (_, i) => i + 7); // 7h às 21h
const HOUR_PX = 48;

// Fundo suave e borda esquerda na cor do tipo (mesmo visual dos agendamentos do módulo de agenda).
const BLOCK_CLASSES: Record<Tone, string> = {
  info: "bg-sky-500/10 border-l-sky-500",
  ai: "bg-violet-500/10 border-l-violet-500",
  success: "bg-emerald-500/10 border-l-emerald-500",
  warning: "bg-amber-500/10 border-l-amber-500",
  danger: "bg-red-500/10 border-l-red-500",
  neutral: "bg-muted border-l-muted-foreground/50",
  primary: "bg-primary/10 border-l-primary",
};

const toDate = (iso: string) => new Date(utcIso(iso));
const toneOf = (event: AgendaEvent): Tone => TYPE_TONES[event.type] ?? "neutral";
const canCancel = (event: AgendaEvent) => event.source === "lm";
const isMidnight = (d: Date) => d.getHours() === 0 && d.getMinutes() === 0;
/** Dia inteiro: marcado assim, ou (espelhos antigos do Google) de meia-noite a meia-noite. */
const isAllDay = (event: AgendaEvent) => !!event.all_day
  || (isMidnight(toDate(event.start)) && isMidnight(toDate(event.end)) && toDate(event.end) > toDate(event.start));
/** O evento aparece no dia: os de dia inteiro em todos os dias que cobrem (o fim é exclusivo). */
const coversDay = (event: AgendaEvent, day: Date) => (isAllDay(event)
  ? toDate(event.start) <= startOfDay(day) && startOfDay(day) < toDate(event.end)
  : isSameDay(toDate(event.start), day));

function errorDetail(error: unknown, fallback: string) {
  return (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail || fallback;
}

/** Primeiro dia e fim (exclusivo) do período de cada visão. */
function rangeFor(view: View, anchor: Date): { from: Date; to: Date } {
  if (view === "day") return { from: startOfDay(anchor), to: addDays(startOfDay(anchor), 1) };
  if (view === "week") {
    const monday = startOfWeek(anchor, { weekStartsOn: 1 });
    return { from: monday, to: addDays(monday, 7) };
  }
  const first = startOfMonth(anchor);
  if (view === "list") return { from: first, to: addMonths(first, 1) };
  const gridStart = startOfWeek(first, { weekStartsOn: 1 });
  return { from: gridStart, to: addDays(gridStart, 42) };
}

function shift(view: View, anchor: Date, direction: 1 | -1): Date {
  if (view === "day") return addDays(anchor, direction);
  if (view === "week") return addDays(anchor, 7 * direction);
  return addMonths(startOfMonth(anchor), direction);
}

function titleFor(view: View, anchor: Date, from: Date, to: Date): string {
  if (view === "day") return format(anchor, "EEEE, d 'de' MMMM 'de' yyyy", { locale: ptBR });
  if (view === "week") return `${format(from, "d 'de' MMM", { locale: ptBR })} — ${format(addDays(to, -1), "d 'de' MMM 'de' yyyy", { locale: ptBR })}`;
  return format(anchor, "MMMM 'de' yyyy", { locale: ptBR });
}

/** Quando o evento acontece, no formato da ficha do Google ("Quarta-feira, 28 de outubro · 12:00 – 13:00"). */
function whenText(event: AgendaEvent) {
  const start = toDate(event.start);
  const end = toDate(event.end);
  if (isAllDay(event)) {
    const last = addDays(end, -1);
    return isSameDay(start, last) ? format(start, "EEEE, d 'de' MMMM", { locale: ptBR })
      : `${format(start, "d 'de' MMM", { locale: ptBR })} – ${format(last, "d 'de' MMM 'de' yyyy", { locale: ptBR })}`;
  }
  return isSameDay(start, end)
    ? `${format(start, "EEEE, d 'de' MMMM", { locale: ptBR })} · ${format(start, "HH:mm")} – ${format(end, "HH:mm")}`
    : `${format(start, "d 'de' MMM, HH:mm", { locale: ptBR })} – ${format(end, "d 'de' MMM, HH:mm", { locale: ptBR })}`;
}

// --- Agendar / editar ------------------------------------------------------------------------

/** Linha do formulário com ícone à esquerda, como no editor de eventos do Google Agenda. */
function FieldRow({ icon: Icon, children, className }: { icon: LucideIcon; children: React.ReactNode; className?: string }) {
  return (
    <div className={cn("flex gap-4", className)}>
      <Icon className="w-5 h-5 mt-2 shrink-0 text-muted-foreground" aria-hidden />
      <div className="flex-1 min-w-0">{children}</div>
    </div>
  );
}

type Saved = AgendaEvent & { warnings: string[] };

/**
 * Criar ou, com `editing`, editar um evento da plataforma no estilo do Google Agenda: título, tipo, data e
 * hora (ou dia inteiro), repetição, cliente, local e descrição. Montado a cada abertura (estado inicial vem
 * do evento ou da faixa clicada). Numa série, o "Salvar" pergunta o alcance (este, este e os seguintes, todos).
 */
function ScheduleDialog({ onClose, leadId, initial, editing = null }: {
  onClose: () => void; leadId: string | null; initial?: { day: string; time: string } | null;
  editing?: AgendaEvent | null;
}) {
  const queryClient = useQueryClient();
  // Aberto pela própria Agenda (sem ?lead=): o cliente é escolhido aqui.
  const [picked, setPicked] = useState<PickedContact | null>(null);
  const customerId = leadId ?? picked?.id ?? null;
  const { data: lead } = useLead(customerId);

  const editStart = editing ? toDate(editing.start) : null;
  const editEnd = editing ? toDate(editing.end) : null;
  const editAllDay = editing ? isAllDay(editing) : false;
  const firstDay = initial?.day ?? format(editStart ?? addDays(new Date(), 1), "yyyy-MM-dd");
  const firstTime = initial?.time ?? (editStart && !editAllDay ? format(editStart, "HH:mm") : "10:00");
  const [type, setType] = useState(editing?.type ?? "reuniao_online");
  const [title, setTitle] = useState(editing?.title ?? "");
  const [allDay, setAllDay] = useState(editAllDay);
  const [day, setDay] = useState(firstDay);
  const [time, setTime] = useState(firstTime);
  const [endDay, setEndDay] = useState(editEnd ? format(editAllDay ? addDays(editEnd, -1) : editEnd, "yyyy-MM-dd") : firstDay);
  const [endTime, setEndTime] = useState(editEnd && !editAllDay ? format(editEnd, "HH:mm")
    : format(addMinutes(new Date(`${firstDay}T${firstTime}:00`), 60), "HH:mm"));
  const [rule, setRule] = useState<RecurrenceRule | null>(editing?.recurrence ?? null);
  const [location, setLocation] = useState(editing?.location ?? "");
  const [notes, setNotes] = useState(editing?.notes ?? "");
  const [notify, setNotify] = useState(true);
  const [askScope, setAskScope] = useState(false);
  const withClient = editing ? !!editing.customer_id : !!customerId;
  const needsClient = type === "reuniao_online" || type === "visita_tecnica";
  const ruleChanged = !sameRule(rule, editing?.recurrence);

  useEffect(() => {
    if (lead?.venue && !editing) setLocation(lead.venue);
  }, [lead?.venue, editing]);

  const startAt = () => new Date(`${day}T${allDay ? "00:00" : time}:00`);
  const endAt = () => (allDay ? addDays(new Date(`${endDay}T00:00:00`), 1) : new Date(`${endDay}T${endTime}:00`));

  // Mudar o início leva o fim junto (mesma duração) e a repetição semanal acompanha o dia, como no Google.
  const changeStartDay = (next: string) => {
    const delta = differenceInCalendarDays(dayToDate(next), dayToDate(day));
    setEndDay(format(addDays(dayToDate(endDay), delta), "yyyy-MM-dd"));
    setRule((current) => followStart(current, dayToDate(day), dayToDate(next)));
    setDay(next);
  };
  const changeStartTime = (next: string) => {
    const duration = (endAt().getTime() - startAt().getTime()) / 60e3;
    const end = addMinutes(new Date(`${day}T${next}:00`), duration > 0 ? duration : 60);
    setTime(next);
    setEndDay(format(end, "yyyy-MM-dd"));
    setEndTime(format(end, "HH:mm"));
  };
  const changeType = (next: string) => {
    setType(next);
    if (next === "evento_confirmado") setAllDay(true); // a data do evento do cliente fica bloqueada o dia todo
  };

  const mutation = useMutation({
    mutationFn: async ({ force = false, scope }: { force?: boolean; scope?: Scope }) => {
      const body = {
        start: startAt().toISOString(), end: endAt().toISOString(), all_day: allDay,
        title: title.trim() || undefined, notes, notify_customer: notify, force: force || undefined,
        location: type !== "reuniao_online" ? location : undefined,
      };
      if (editing) {
        // Evento único: a repetição vai junto (e passa a valer para "todos"). Série: só fora do "este evento".
        const series = !!editing.series_id;
        const effective = series ? scope ?? "this" : rule ? "all" : "this";
        return (await api.patch<Saved>(`/agenda/events/${editing.id}/`, {
          ...body, scope: effective, ...(effective !== "this" || !series ? { recurrence: rule } : {}),
        })).data;
      }
      return (await api.post<Saved>("/agenda/events/", {
        ...body, type, customer_id: customerId || undefined, recurrence: rule || undefined,
        location: type !== "reuniao_online" && location ? location : undefined, notes: notes || undefined,
      })).data;
    },
    onSuccess: (event) => {
      toast.success(editing ? "Evento atualizado." : event.meet_link ? "Agendado com link do Meet." : "Agendado.");
      event.warnings?.forEach((w) => toast.warning(w));
      queryClient.invalidateQueries({ queryKey: ["agenda"] });
      queryClient.invalidateQueries({ queryKey: ["lead", customerId] });
      queryClient.invalidateQueries({ queryKey: ["funnel"] });
      onClose();
    },
    onError: (error, variables) => {
      // 409: horário ocupado (bloqueio, reunião, visita ou compromisso do Google). Só a Erica força.
      const data = (error as { response?: { status?: number; data?: { can_force?: boolean } } })?.response;
      if (data?.status === 409 && data.data?.can_force
          && window.confirm(`${errorDetail(error, "Horário ocupado.")}

Agendar mesmo assim?`)) {
        mutation.mutate({ ...variables, force: true });
        return;
      }
      toast.error(errorDetail(error, editing ? "Não foi possível salvar." : "Não foi possível agendar."));
    },
  });

  const save = () => {
    if (endAt() <= startAt()) {
      toast.error("O fim deve ser depois do início.");
      return;
    }
    if (editing?.series_id) setAskScope(true);
    else mutation.mutate({});
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-xl p-0 gap-0 max-h-[92vh] overflow-y-auto">
        <DialogHeader className="sr-only">
          <DialogTitle>{editing ? "Editar evento" : "Novo agendamento"}</DialogTitle>
          <DialogDescription>Título, data e hora, repetição e detalhes do evento.</DialogDescription>
        </DialogHeader>
        <div className="px-6 pt-7 pb-5 space-y-5">
          <div className="pl-9 space-y-3">
            <input value={title} onChange={(e) => setTitle(e.target.value)} aria-label="Título" autoFocus={!editing}
              placeholder={customerId || withClient ? "Adicionar título (automático: tipo e cliente)" : "Adicionar título"}
              className="w-full bg-transparent text-xl sm:text-2xl text-foreground border-0 border-b border-border/70 pb-1.5 outline-none focus:border-primary transition-colors placeholder:text-muted-foreground/70" />
            {editing ? (
              <StatusBadge tone={toneOf(editing)}>{editing.type_label}</StatusBadge>
            ) : (
              <div className="flex flex-wrap gap-1.5" role="radiogroup" aria-label="Tipo">
                {TYPE_CHIPS.map(([value, label]) => (
                  <button key={value} type="button" role="radio" aria-checked={type === value} onClick={() => changeType(value)}
                    className={cn("h-8 px-3 rounded-md text-sm font-medium transition-colors",
                      type === value ? "bg-primary/15 text-primary" : "text-muted-foreground hover:bg-secondary")}>
                    {label}
                  </button>
                ))}
              </div>
            )}
          </div>

          <FieldRow icon={Clock}>
            <div className="flex flex-wrap items-center gap-1.5">
              <DateField label="Data de início" value={day} onChange={changeStartDay} />
              {!allDay && <TimeSelect label="Hora de início" value={time} onChange={changeStartTime} />}
              <span className="px-1 text-sm text-muted-foreground">até</span>
              {!allDay && <TimeSelect label="Hora de término" value={endTime} onChange={setEndTime} after={endDay === day ? time : undefined} />}
              <DateField label="Data de término" value={endDay} onChange={setEndDay} />
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-2">
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <Checkbox checked={allDay} onCheckedChange={(v) => setAllDay(v === true)} /> Dia inteiro
              </label>
              <RecurrenceSelect rule={rule} start={dayToDate(day)} onChange={setRule} />
            </div>
          </FieldRow>

          <FieldRow icon={UserRound}>
            {editing || leadId ? (
              <p className="py-2 text-sm text-foreground">{editing?.customer_name || lead?.name || (withClient ? "Cliente" : "Sem cliente")}</p>
            ) : picked ? (
              <div className="flex items-center gap-3 rounded-xl border border-border/60 bg-card px-3 py-2">
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-semibold text-foreground truncate">{picked.name || lead?.name || "Contato selecionado"}</span>
                  {(picked.phone || lead?.phone) && (
                    <span className="block text-xs text-muted-foreground">{phoneDisplay(picked.phone || lead?.phone)}</span>
                  )}
                </span>
                <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0" title="Trocar cliente" onClick={() => setPicked(null)}>
                  <X className="w-4 h-4" />
                </Button>
              </div>
            ) : (
              <ContactPicker className="sm:w-full" onPick={setPicked}
                placeholder={needsClient ? "Adicionar cliente (nome ou telefone)" : "Adicionar cliente (opcional)"} />
            )}
          </FieldRow>

          {type === "reuniao_online" ? (
            <FieldRow icon={Video}>
              {editing?.meet_link ? (
                <a href={editing.meet_link} target="_blank" rel="noreferrer" className="inline-block py-2 text-sm text-sky-600 dark:text-sky-400 hover:underline">
                  Entrar com o Google Meet
                </a>
              ) : (
                <p className="py-2 text-sm text-muted-foreground">Videoconferência do Google Meet criada ao salvar</p>
              )}
            </FieldRow>
          ) : (
            <FieldRow icon={MapPin}>
              <Input value={location} onChange={(e) => setLocation(e.target.value)} aria-label="Local"
                placeholder={type === "visita_tecnica" ? "Adicionar endereço do local (obrigatório)" : "Adicionar local"}
                className="border-0 bg-secondary/50" />
            </FieldRow>
          )}

          <FieldRow icon={AlignLeft}>
            <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} aria-label="Descrição" placeholder="Adicionar descrição"
              className="min-h-[88px] border-0 bg-secondary/50" />
          </FieldRow>

          {withClient && needsClient && (
            <FieldRow icon={MessageCircle}>
              <div className="flex items-center gap-2 py-1.5">
                <Switch id="notify" checked={notify} onCheckedChange={setNotify} />
                <Label htmlFor="notify" className="text-sm font-normal">
                  {editing ? "Avisar o cliente por WhatsApp se mudar o horário" : "Enviar confirmação ao cliente por WhatsApp"}
                </Label>
              </div>
            </FieldRow>
          )}
        </div>
        <div className="sticky bottom-0 flex justify-end gap-2 border-t border-border/50 bg-background/95 px-6 py-3">
          <Button variant="ghost" onClick={onClose}>Cancelar</Button>
          <Button onClick={save} disabled={mutation.isPending}>
            {mutation.isPending && <Loader2 className="w-4 h-4 mr-2 animate-spin" />} Salvar
          </Button>
        </div>
      </DialogContent>
      {askScope && (
        <ScopeDialog action="edit" allowThis={!ruleChanged} onClose={() => setAskScope(false)}
          onConfirm={(scope) => { setAskScope(false); mutation.mutate({ scope }); }} />
      )}
    </Dialog>
  );
}

// --- Ficha do evento -----------------------------------------------------------------------

function EventDetailsDialog({ event, onClose, onCancel, onEdit }: {
  event: AgendaEvent | null; onClose: () => void; onCancel: (event: AgendaEvent) => void; onEdit: (event: AgendaEvent) => void;
}) {
  const navigate = useNavigate();
  if (!event) return null;
  const start = toDate(event.start);
  const rows: [LucideIcon, React.ReactNode][] = [];
  if (event.customer_name) rows.push([UserRound, event.customer_name]);
  if (event.location) rows.push([MapPin, event.location]);
  if (event.notes) rows.push([AlignLeft, <span className="whitespace-pre-line">{event.notes}</span>]);
  rows.push([CalendarPlus, event.source === "lm"
    ? `Plataforma${event.sync_status ? ` · No Google: ${SYNC_LABELS[event.sync_status] ?? event.sync_status}` : ""}`
    : "Google Agenda"]);
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-md">
        {canCancel(event) && (
          <div className="absolute right-12 top-3 flex gap-1">
            <Button variant="ghost" size="icon" className="h-8 w-8" title="Editar evento" onClick={() => onEdit(event)}>
              <Pencil className="w-4 h-4" />
            </Button>
            <Button variant="ghost" size="icon" className="h-8 w-8" title="Excluir evento" onClick={() => onCancel(event)}>
              <Trash2 className="w-4 h-4" />
            </Button>
          </div>
        )}
        <DialogHeader className="pt-6">
          <DialogTitle className="flex items-start gap-3 text-xl font-normal">
            <span className={cn("mt-2 w-3.5 h-3.5 rounded shrink-0", TONE_DOT_CLASSES[toneOf(event)])} />
            <span className="min-w-0 break-words">{event.title}</span>
          </DialogTitle>
          <DialogDescription className="pl-[26px] text-sm text-foreground/80 first-letter:uppercase">
            {whenText(event)}
          </DialogDescription>
          {event.recurrence && (
            <p className="pl-[26px] flex items-center gap-1.5 text-sm text-muted-foreground">
              <Repeat className="w-3.5 h-3.5" /> {describeRule(event.recurrence, start)}
            </p>
          )}
        </DialogHeader>
        <div className="space-y-3 text-sm">
          <div className="pl-[26px]"><StatusBadge tone={toneOf(event)}>{event.type_label}</StatusBadge></div>
          {event.meet_link && (
            <a href={event.meet_link} target="_blank" rel="noreferrer"
              className="ml-[26px] inline-flex items-center gap-2 rounded-lg bg-sky-600 px-3 py-2 text-sm font-medium text-white hover:bg-sky-700">
              <Video className="w-4 h-4" /> Participar com o Google Meet
            </a>
          )}
          {rows.map(([Icon, value], i) => (
            <div key={i} className="flex gap-3">
              <Icon className="w-4 h-4 mt-0.5 shrink-0 text-muted-foreground" />
              <span className="min-w-0 break-words text-foreground">{value}</span>
            </div>
          ))}
        </div>
        {event.customer_id && (
          <div className="flex justify-end">
            <Button variant="outline" onClick={() => navigate(`/funil?lead=${event.customer_id}`)}>
              <SquareKanban className="w-4 h-4 mr-2" /> Abrir lead
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

// --- Visões --------------------------------------------------------------------------------

function EventBlock({ event, onOpen, compact = false }: { event: AgendaEvent; onOpen: (e: AgendaEvent) => void; compact?: boolean }) {
  const start = toDate(event.start);
  const end = toDate(event.end);
  const tone = toneOf(event);
  const allDay = isAllDay(event);
  return (
    <button type="button" onClick={(e) => { e.stopPropagation(); onOpen(event); }}
      title={allDay ? event.title : `${format(start, "HH:mm")} ${event.title}`}
      className={cn("w-full h-full rounded-md border border-border/60 border-l-4 px-2 py-1 text-left text-[11px] leading-tight overflow-hidden text-foreground",
        "transition-all hover:shadow-md hover:z-10", BLOCK_CLASSES[tone])}>
      <span className={cn("block font-semibold truncate", tone === "neutral" ? "text-muted-foreground" : "")}>
        <span className={cn("inline-block w-1.5 h-1.5 rounded-full mr-1 align-middle", TONE_DOT_CLASSES[tone])} />
        {!allDay && `${format(start, "HH:mm")} `}{event.title}
        {event.series_id && <Repeat className="inline w-3 h-3 ml-1 align-[-2px] opacity-60" aria-label="Repete" />}
      </span>
      {!compact && !allDay && <span className="block truncate text-muted-foreground">até {format(end, "HH:mm")}{event.meet_link ? " · Meet" : event.location ? ` · ${event.location}` : ""}</span>}
    </button>
  );
}

function TimeGrid({ days, eventsOf, onOpen, onSlot }: {
  days: Date[]; eventsOf: (day: Date) => AgendaEvent[]; onOpen: (e: AgendaEvent) => void; onSlot: (day: Date, hour: number) => void;
}) {
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 60000);
    return () => window.clearInterval(timer);
  }, []);
  const nowTop = (now.getHours() + now.getMinutes() / 60 - HOURS[0]) * HOUR_PX;
  const single = days.length === 1;
  const allDayOf = (day: Date) => eventsOf(day).filter(isAllDay);
  const hasAllDay = days.some((day) => allDayOf(day).length > 0);

  return (
    <div className="overflow-x-auto">
      <div className={cn(!single && "min-w-[760px]")}>
        <div className="sticky top-0 bg-card z-20 border-b border-border/50">
          <div className="flex">
            <div className="w-14 shrink-0" />
            {days.map((day) => {
              const today = isSameDay(day, now);
              return (
                <div key={day.toISOString()} className="flex-1 border-l border-border/50 py-2 text-center">
                  <div className="text-[11px] uppercase tracking-wide text-muted-foreground">{format(day, "EEE", { locale: ptBR })}</div>
                  <div className={cn("mx-auto mt-0.5 w-8 h-8 grid place-items-center rounded-full text-sm font-semibold",
                    today ? "bg-primary text-primary-foreground" : "text-foreground")}>{format(day, "d")}</div>
                </div>
              );
            })}
          </div>
          {hasAllDay && (
            <div className="flex border-t border-border/30">
              <div className="w-14 shrink-0 pr-2 pt-1.5 text-right text-[10px] text-muted-foreground">dia todo</div>
              {days.map((day) => (
                <div key={day.toISOString()} className="flex-1 min-w-0 border-l border-border/50 p-1 space-y-1">
                  {allDayOf(day).map((event) => <div key={event.id} className="h-6"><EventBlock event={event} onOpen={onOpen} compact /></div>)}
                </div>
              ))}
            </div>
          )}
        </div>
        <div className="flex">
          <div className="w-14 shrink-0 sticky left-0 z-[15] bg-card">
            {HOURS.map((h) => (
              <div key={h} style={{ height: HOUR_PX }} className="text-[11px] text-muted-foreground text-right pr-2 pt-1 border-b border-border/30">
                {String(h).padStart(2, "0")}:00
              </div>
            ))}
          </div>
          {days.map((day) => {
            const today = isSameDay(day, now);
            return (
              <div key={day.toISOString()} className={cn("flex-1 relative border-l border-border/50", !single && "min-w-[100px]")}
                style={{ height: HOURS.length * HOUR_PX }}>
                {HOURS.map((h) => (
                  <button key={h} type="button" style={{ height: HOUR_PX }} onClick={() => onSlot(day, h)}
                    title={`Agendar ${format(day, "dd/MM")} às ${String(h).padStart(2, "0")}:00`}
                    className="w-full border-b border-border/30 flex items-center justify-center group hover:bg-primary/10 transition-colors">
                    <Plus className="w-3.5 h-3.5 text-primary opacity-0 group-hover:opacity-70" />
                  </button>
                ))}
                {today && nowTop >= 0 && nowTop <= HOURS.length * HOUR_PX && (
                  <div className="absolute inset-x-0 z-10 pointer-events-none" style={{ top: nowTop }}>
                    <div className="h-px bg-red-500" />
                    <div className="absolute -left-1 -top-1 w-2 h-2 rounded-full bg-red-500" />
                  </div>
                )}
                {eventsOf(day).filter((event) => !isAllDay(event)).map((event) => {
                  const start = toDate(event.start);
                  const end = toDate(event.end);
                  const sameDayEnd = isSameDay(start, end) ? end : new Date(start.getFullYear(), start.getMonth(), start.getDate(), 22);
                  const top = Math.max(0, (start.getHours() + start.getMinutes() / 60 - HOURS[0]) * HOUR_PX);
                  const height = Math.max(24, ((sameDayEnd.getTime() - start.getTime()) / 3600e3) * HOUR_PX);
                  return (
                    <div key={event.id} className="absolute inset-x-1 z-[5]" style={{ top, height: Math.min(height, HOURS.length * HOUR_PX - top) }}>
                      <EventBlock event={event} onOpen={onOpen} compact={height < 40} />
                    </div>
                  );
                })}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function DayList({ days, eventsOf, onOpen }: { days: Date[]; eventsOf: (day: Date) => AgendaEvent[]; onOpen: (e: AgendaEvent) => void }) {
  return (
    <ul className="divide-y divide-border/50">
      {days.map((day) => {
        const items = eventsOf(day);
        const today = isSameDay(day, new Date());
        return (
          <li key={day.toISOString()} className="px-4 py-3">
            <h3 className={cn("text-sm font-semibold first-letter:uppercase mb-2", today ? "text-primary" : "text-foreground")}>
              {format(day, "EEEE, dd/MM", { locale: ptBR })}
            </h3>
            {items.length === 0 ? (
              <p className="text-xs text-muted-foreground">Livre</p>
            ) : (
              <div className="space-y-1.5">{items.map((e) => <div key={e.id} className={isAllDay(e) ? "h-7" : "h-12"}><EventBlock event={e} onOpen={onOpen} /></div>)}</div>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function MonthGrid({ from, anchor, eventsOf, onDay, onOpen }: {
  from: Date; anchor: Date; eventsOf: (day: Date) => AgendaEvent[]; onDay: (day: Date) => void; onOpen: (e: AgendaEvent) => void;
}) {
  const cells = Array.from({ length: 42 }, (_, i) => addDays(from, i));
  const weeks = cells.slice(35).every((d) => !isSameMonth(d, anchor)) ? cells.slice(0, 35) : cells;
  return (
    <div className="p-1 sm:p-3">
      <div className="grid grid-cols-7 gap-1 mb-1">
        {WEEKDAYS.map((label) => (
          <div key={label} className="text-center text-[11px] uppercase tracking-wide text-muted-foreground py-1">{label}</div>
        ))}
      </div>
      <div className="grid grid-cols-7 gap-1">
        {weeks.map((day) => {
          const items = eventsOf(day);
          const today = isSameDay(day, new Date());
          return (
            <div key={day.toISOString()} role="button" tabIndex={0} onClick={() => onDay(day)}
              onKeyDown={(e) => e.key === "Enter" && onDay(day)}
              className={cn("min-h-[56px] sm:min-h-[96px] min-w-0 rounded-lg border border-border/50 p-1 sm:p-2 text-left transition-colors hover:border-primary/50 hover:bg-primary/5 cursor-pointer",
                !isSameMonth(day, anchor) && "opacity-40", today && "border-primary/60 bg-primary/5")}>
              <span className={cn("text-sm font-semibold", today ? "text-primary" : "text-foreground")}>{format(day, "d")}</span>
              {items.length > 0 && <span className="sm:hidden block text-[11px] text-foreground">{items.length}</span>}
              <div className="hidden sm:block mt-1 space-y-0.5">
                {items.slice(0, 3).map((e) => (
                  <button key={e.id} type="button" onClick={(ev) => { ev.stopPropagation(); onOpen(e); }}
                    className={cn("w-full flex items-center gap-1 text-[11px] text-left truncate rounded px-1 hover:bg-muted",
                      isAllDay(e) && BLOCK_CLASSES[toneOf(e)])}>
                    <span className={cn("w-1.5 h-1.5 rounded-full shrink-0", TONE_DOT_CLASSES[toneOf(e)])} />
                    {!isAllDay(e) && <span className="tabular-nums text-muted-foreground">{format(toDate(e.start), "HH:mm")}</span>}
                    <span className="truncate text-foreground">{e.title}</span>
                  </button>
                ))}
                {items.length > 3 && <span className="block px-1 text-[11px] text-muted-foreground">+{items.length - 3} mais</span>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ListTable({ events, onOpen }: { events: AgendaEvent[]; onOpen: (e: AgendaEvent) => void }) {
  if (events.length === 0) return <p className="p-8 text-center text-sm text-muted-foreground">Nenhum compromisso no período.</p>;
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Data</TableHead>
            <TableHead>Hora</TableHead>
            <TableHead>Compromisso</TableHead>
            <TableHead className="hidden md:table-cell">Cliente</TableHead>
            <TableHead>Tipo</TableHead>
            <TableHead className="hidden lg:table-cell">Local</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {events.map((event) => {
            const start = toDate(event.start);
            return (
              <TableRow key={event.id} className="cursor-pointer" onClick={() => onOpen(event)}>
                <TableCell className="whitespace-nowrap first-letter:uppercase">{format(start, "EEE dd/MM", { locale: ptBR })}</TableCell>
                <TableCell className="tabular-nums whitespace-nowrap">
                  {isAllDay(event) ? "Dia inteiro" : `${format(start, "HH:mm")}–${format(toDate(event.end), "HH:mm")}`}
                </TableCell>
                <TableCell className="font-medium text-foreground">
                  {event.title}
                  {event.series_id && <Repeat className="inline w-3.5 h-3.5 ml-1.5 align-[-2px] text-muted-foreground" aria-label="Repete" />}
                </TableCell>
                <TableCell className="hidden md:table-cell">{event.customer_name || "—"}</TableCell>
                <TableCell><StatusBadge tone={toneOf(event)}>{event.type_label}</StatusBadge></TableCell>
                <TableCell className="hidden lg:table-cell">
                  {event.meet_link ? (
                    <span className="inline-flex items-center gap-1 text-sky-600 dark:text-sky-400"><Video className="w-3.5 h-3.5" /> Meet</span>
                  ) : event.location ? (
                    <span className="inline-flex items-center gap-1"><MapPin className="w-3.5 h-3.5 text-muted-foreground" /> {event.location}</span>
                  ) : "—"}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}

// --- Página --------------------------------------------------------------------------------

export default function Agenda() {
  const queryClient = useQueryClient();
  const [params, setParams] = useSearchParams();
  const leadId = params.get("lead");
  const [view, setView] = useState<View>("week");
  const [anchor, setAnchor] = useState(() => new Date());
  const [scheduleOpen, setScheduleOpen] = useState(!!leadId);
  const [slot, setSlot] = useState<{ day: string; time: string } | null>(null);
  const [selected, setSelected] = useState<AgendaEvent | null>(null);
  const [editing, setEditing] = useState<AgendaEvent | null>(null);
  const [deleting, setDeleting] = useState<AgendaEvent | null>(null);
  const { data: me } = useCurrentUser();
  const { from, to } = rangeFor(view, anchor);

  useEffect(() => {
    const google = params.get("google");
    if (google === "ok") toast.success("Google Agenda conectado.");
    if (google === "erro" || google === "negado") toast.error("Não foi possível conectar o Google Agenda.");
  }, [params]);

  const { data: events = [], isFetching } = useQuery({
    queryKey: ["agenda", from.toISOString(), to.toISOString()],
    queryFn: async () => (await api.get<AgendaEvent[]>("/agenda/events/", {
      params: { start: from.toISOString(), end: to.toISOString() },
    })).data,
    refetchInterval: 60000,
  });

  const { data: google } = useQuery({
    queryKey: ["agenda-google-status"],
    queryFn: async () => (await api.get<GoogleStatus>("/agenda/google/status/")).data,
  });

  const sync = useMutation({
    mutationFn: async () => (await api.post("/agenda/google/sync/")).data,
    onSuccess: () => {
      toast.success("Agenda sincronizada com o Google.");
      queryClient.invalidateQueries({ queryKey: ["agenda"] });
    },
    onError: (error) => toast.error(errorDetail(error, "Falha ao sincronizar.")),
  });

  const connect = async () => {
    try {
      const { data } = await api.get<{ url: string }>("/agenda/google/connect/");
      window.location.href = data.url;
    } catch (error) {
      toast.error(errorDetail(error, "Não foi possível iniciar a conexão."));
    }
  };

  const remove = async (event: AgendaEvent, scope: Scope = "this") => {
    try {
      await api.delete(`/agenda/events/${event.id}/`, { params: { scope } });
      toast.success(scope === "this" ? "Evento excluído." : "Eventos excluídos.");
      setSelected(null);
      setDeleting(null);
      queryClient.invalidateQueries({ queryKey: ["agenda"] });
    } catch (error) {
      toast.error(errorDetail(error, "Não foi possível excluir."));
    }
  };
  // Evento que se repete: pergunta o alcance, como o Google. Evento único: confirma e exclui.
  const cancel = (event: AgendaEvent) => {
    if (event.series_id) setDeleting(event);
    else if (window.confirm(`Excluir "${event.title}"? O horário fica livre de novo.`)) remove(event);
  };

  const sorted = useMemo(() => [...events].sort((a, b) =>
    Number(isAllDay(b)) - Number(isAllDay(a)) || toDate(a.start).getTime() - toDate(b.start).getTime()), [events]);
  const eventsOf = (day: Date) => sorted.filter((e) => coversDay(e, day));
  const weekDays = useMemo(() => Array.from({ length: 7 }, (_, i) => addDays(from, i)), [from]);

  const openSchedule = (initial?: { day: string; time: string }) => {
    setSlot(initial ?? null);
    setScheduleOpen(true);
  };
  const closeSchedule = () => {
    setScheduleOpen(false);
    setSlot(null);
    if (leadId) {
      const next = new URLSearchParams(params);
      next.delete("lead");
      setParams(next, { replace: true });
    }
  };
  const onSlot = (day: Date, hour: number) => openSchedule({ day: format(day, "yyyy-MM-dd"), time: `${String(hour).padStart(2, "0")}:00` });
  const openDay = (day: Date) => { setAnchor(day); setView("day"); };

  return (
    <PageShell
      title="Agenda da Erica"
      maxWidthClassName="max-w-7xl"
      actions={(
        <>
          {google?.connected ? (
            <Button variant="outline" size="icon" className="sm:w-auto sm:px-4" onClick={() => sync.mutate()} disabled={sync.isPending} title="Sincronizar com o Google">
              <RefreshCw className={cn("w-4 h-4 sm:mr-2", sync.isPending && "animate-spin")} /> <span className="hidden sm:inline">Sincronizar</span>
            </Button>
          ) : isAdminUser(me) && google?.client_configured ? (
            <Button variant="outline" onClick={connect}><Link2 className="w-4 h-4 sm:mr-2" /> <span className="hidden sm:inline">Conectar Google</span></Button>
          ) : null}
          <Button onClick={() => openSchedule()}><CalendarPlus className="w-4 h-4 sm:mr-2" /> <span className="hidden sm:inline">Agendar</span></Button>
        </>
      )}
    >
      <FilterBar
        right={(
          <Tabs value={view} onValueChange={(v) => setView(v as View)}>
            <TabsList>
              <TabsTrigger value="day">Dia</TabsTrigger>
              <TabsTrigger value="week">Semana</TabsTrigger>
              <TabsTrigger value="month">Mês</TabsTrigger>
              <TabsTrigger value="list">Lista</TabsTrigger>
            </TabsList>
          </Tabs>
        )}
      >
        <Button variant="outline" size="icon" onClick={() => setAnchor(shift(view, anchor, -1))} title="Anterior"><ChevronLeft className="w-4 h-4" /></Button>
        <Button variant="outline" size="icon" onClick={() => setAnchor(shift(view, anchor, 1))} title="Próximo"><ChevronRight className="w-4 h-4" /></Button>
        <Button variant="outline" size="sm" onClick={() => setAnchor(new Date())}>Hoje</Button>
        <span className="ml-2 text-sm sm:text-base font-semibold text-foreground first-letter:uppercase">{titleFor(view, anchor, from, to)}</span>
        {isFetching && <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />}
      </FilterBar>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <Legend items={TYPE_LEGEND.map((t) => ({ label: t.label, colorClass: TONE_DOT_CLASSES[TYPE_TONES[t.type]] }))} />
        {google && (
          <StatusBadge tone={google.connected ? "success" : "warning"}
            className="whitespace-normal">
            {google.connected ? "Google Agenda conectado"
              : `Google Agenda não conectado: os agendamentos ficam só na plataforma${google.client_configured ? "" : " (falta o client secret)"}`}
          </StatusBadge>
        )}
      </div>

      <div className="glass rounded-2xl border border-border/50 overflow-hidden">
        {view === "day" && <TimeGrid days={[startOfDay(anchor)]} eventsOf={eventsOf} onOpen={setSelected} onSlot={onSlot} />}
        {view === "week" && (
          <>
            <div className="hidden md:block"><TimeGrid days={weekDays} eventsOf={eventsOf} onOpen={setSelected} onSlot={onSlot} /></div>
            <div className="md:hidden"><DayList days={weekDays} eventsOf={eventsOf} onOpen={setSelected} /></div>
          </>
        )}
        {view === "month" && <MonthGrid from={from} anchor={anchor} eventsOf={eventsOf} onDay={openDay} onOpen={setSelected} />}
        {view === "list" && <ListTable events={sorted} onOpen={setSelected} />}
      </div>

      {editing && <ScheduleDialog key={editing.id} onClose={() => setEditing(null)} leadId={null} editing={editing} />}
      {!editing && scheduleOpen && (
        <ScheduleDialog key={slot ? `${slot.day}-${slot.time}` : "novo"} onClose={closeSchedule} leadId={leadId} initial={slot} />
      )}
      <EventDetailsDialog event={selected} onClose={() => setSelected(null)} onCancel={cancel}
        onEdit={(event) => { setSelected(null); setEditing(event); }} />
      {deleting && <ScopeDialog action="delete" onClose={() => setDeleting(null)} onConfirm={(scope) => remove(deleting, scope)} />}
    </PageShell>
  );
}
