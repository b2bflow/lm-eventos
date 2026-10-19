import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { addDays, addMonths, format, isSameDay, isSameMonth, startOfDay, startOfMonth, startOfWeek } from "date-fns";
import { ptBR } from "date-fns/locale";
import { toast } from "sonner";
import { CalendarPlus, ChevronLeft, ChevronRight, Link2, Loader2, MapPin, Plus, RefreshCw, SquareKanban, Video } from "lucide-react";
import { PageShell } from "@/components/shared/PageShell";
import { FilterBar, Legend } from "@/components/shared/FilterBar";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import api from "@/services/api";
import { cn } from "@/lib/utils";
import { utcIso } from "@/lib/format";
import { TONE_DOT_CLASSES, type Tone } from "@/lib/tones";
import { isAdminUser, useCurrentUser, useLead } from "@/hooks/useFunnel";

interface AgendaEvent {
  id: string;
  type: string;
  type_label: string;
  title: string;
  customer_id?: string | null;
  customer_name?: string | null;
  start: string;
  end: string;
  location?: string | null;
  meet_link?: string | null;
  source: string;
  sync_status?: string;
  fixed?: boolean;
}

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

const TYPE_OPTIONS: Record<string, string> = {
  reuniao_online: "Reunião online (gera link do Meet)",
  visita_tecnica: "Visita técnica",
  evento_confirmado: "Evento confirmado (bloqueia a data)",
  bloqueio: "Bloqueio",
};

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
const canCancel = (event: AgendaEvent) => !event.fixed && event.source === "lm";

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

// --- Agendar -------------------------------------------------------------------------------

function ScheduleDialog({ open, onClose, leadId, initial }: {
  open: boolean; onClose: () => void; leadId: string | null; initial?: { day: string; time: string } | null;
}) {
  const queryClient = useQueryClient();
  const { data: lead } = useLead(leadId);
  const [type, setType] = useState("reuniao_online");
  const [day, setDay] = useState(format(addDays(new Date(), 1), "yyyy-MM-dd"));
  const [time, setTime] = useState("10:00");
  const [duration, setDuration] = useState(60);
  const [location, setLocation] = useState("");
  const [notes, setNotes] = useState("");
  const [notify, setNotify] = useState(true);

  useEffect(() => {
    if (lead?.venue) setLocation(lead.venue);
  }, [lead?.venue]);

  // Clique numa faixa livre da grade: já abre no dia e na hora clicados.
  useEffect(() => {
    if (open && initial) {
      setDay(initial.day);
      setTime(initial.time);
    }
  }, [open, initial]);

  const mutation = useMutation({
    mutationFn: async (force: boolean = false) => {
      const start = new Date(`${day}T${time}:00`);
      const end = type === "evento_confirmado" && duration < 60 ? new Date(start.getTime() + 6 * 3600e3) : new Date(start.getTime() + duration * 60e3);
      return (await api.post("/agenda/events/", {
        type, customer_id: leadId || undefined, start: start.toISOString(), end: end.toISOString(),
        location: type !== "reuniao_online" && location ? location : undefined, notes: notes || undefined, notify_customer: notify,
        force: force || undefined,
      })).data as AgendaEvent & { warnings: string[] };
    },
    onSuccess: (event) => {
      toast.success(event.meet_link ? "Agendado com link do Meet." : "Agendado.");
      event.warnings?.forEach((w) => toast.warning(w));
      queryClient.invalidateQueries({ queryKey: ["agenda"] });
      queryClient.invalidateQueries({ queryKey: ["lead", leadId] });
      queryClient.invalidateQueries({ queryKey: ["funnel"] });
      onClose();
    },
    onError: (error) => {
      // 409: horário ocupado (treino, reunião, visita ou compromisso do Google). Só a Erica força.
      const data = (error as { response?: { status?: number; data?: { can_force?: boolean } } })?.response;
      if (data?.status === 409 && data.data?.can_force
          && window.confirm(`${errorDetail(error, "Horário ocupado.")}

Agendar mesmo assim?`)) {
        mutation.mutate(true);
        return;
      }
      toast.error(errorDetail(error, "Não foi possível agendar."));
    },
  });

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Agendar{lead ? `: ${lead.name || lead.phone}` : ""}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1">
            <Label className="text-xs">Tipo</Label>
            <Select value={type} onValueChange={setType}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {Object.entries(TYPE_OPTIONS).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="grid grid-cols-3 gap-2">
            <div className="space-y-1 col-span-3 sm:col-span-1">
              <Label className="text-xs">Dia</Label>
              <Input type="date" value={day} onChange={(e) => setDay(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Início</Label>
              <Input type="time" value={time} onChange={(e) => setTime(e.target.value)} />
            </div>
            <div className="space-y-1 col-span-2 sm:col-span-1">
              <Label className="text-xs">Duração (min)</Label>
              <Input type="number" min={15} step={15} value={duration} onChange={(e) => setDuration(Number(e.target.value) || 60)} />
            </div>
          </div>
          {type !== "reuniao_online" && (
            <div className="space-y-1">
              <Label className="text-xs">{type === "visita_tecnica" ? "Endereço do local" : "Local"}</Label>
              <Input value={location} onChange={(e) => setLocation(e.target.value)} />
            </div>
          )}
          <div className="space-y-1">
            <Label className="text-xs">Observações</Label>
            <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} />
          </div>
          {leadId && (type === "reuniao_online" || type === "visita_tecnica") && (
            <div className="flex items-center gap-2">
              <Switch id="notify" checked={notify} onCheckedChange={setNotify} />
              <Label htmlFor="notify" className="text-sm">Enviar confirmação ao cliente por WhatsApp</Label>
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancelar</Button>
          <Button onClick={() => mutation.mutate(false)} disabled={mutation.isPending}>Agendar</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// --- Ficha do evento -----------------------------------------------------------------------

function EventDetailsDialog({ event, onClose, onCancel }: {
  event: AgendaEvent | null; onClose: () => void; onCancel: (event: AgendaEvent) => void;
}) {
  const navigate = useNavigate();
  if (!event) return null;
  const start = toDate(event.start);
  const end = toDate(event.end);
  const sameDay = isSameDay(start, end);
  const rows: [string, React.ReactNode][] = [
    ["Quando", sameDay
      ? `${format(start, "EEEE, dd/MM/yyyy", { locale: ptBR })} · ${format(start, "HH:mm")}–${format(end, "HH:mm")}`
      : `${format(start, "dd/MM HH:mm")} até ${format(end, "dd/MM HH:mm")}`],
    ["Cliente", event.customer_name || "—"],
    ["Local", event.location || "—"],
    ["Origem", event.source === "lm" ? "Plataforma" : "Google Agenda"],
  ];
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex flex-wrap items-center gap-x-3 gap-y-1 pr-6">
            {event.title}
            <StatusBadge tone={toneOf(event)}>{event.type_label}</StatusBadge>
          </DialogTitle>
          <DialogDescription className="first-letter:uppercase">{format(start, "EEEE", { locale: ptBR })}</DialogDescription>
        </DialogHeader>
        <dl className="grid grid-cols-[90px_1fr] gap-y-2 text-sm">
          {rows.map(([label, value]) => (
            <div key={label} className="contents">
              <dt className="text-muted-foreground">{label}</dt>
              <dd className="text-foreground min-w-0 break-words first-letter:uppercase">{value}</dd>
            </div>
          ))}
        </dl>
        {event.meet_link && (
          <a href={event.meet_link} target="_blank" rel="noreferrer"
            className="inline-flex items-center gap-2 rounded-lg border border-sky-500/30 bg-sky-500/10 px-3 py-2 text-sm text-sky-700 dark:text-sky-300 hover:bg-sky-500/15">
            <Video className="w-4 h-4" /> Entrar no Google Meet
          </a>
        )}
        <DialogFooter className="gap-2 sm:gap-2">
          {event.customer_id && (
            <Button variant="outline" onClick={() => navigate(`/funil?lead=${event.customer_id}`)}>
              <SquareKanban className="w-4 h-4 mr-2" /> Abrir lead
            </Button>
          )}
          {canCancel(event) && (
            <Button variant="destructive" onClick={() => onCancel(event)}>Cancelar evento</Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// --- Visões --------------------------------------------------------------------------------

function EventBlock({ event, onOpen, compact = false }: { event: AgendaEvent; onOpen: (e: AgendaEvent) => void; compact?: boolean }) {
  const start = toDate(event.start);
  const end = toDate(event.end);
  const tone = toneOf(event);
  return (
    <button type="button" onClick={(e) => { e.stopPropagation(); onOpen(event); }}
      title={`${format(start, "HH:mm")} ${event.title}`}
      className={cn("w-full h-full rounded-md border border-border/60 border-l-4 px-2 py-1 text-left text-[11px] leading-tight overflow-hidden text-foreground",
        "transition-all hover:shadow-md hover:z-10", BLOCK_CLASSES[tone])}>
      <span className={cn("block font-semibold truncate", tone === "neutral" ? "text-muted-foreground" : "")}>
        <span className={cn("inline-block w-1.5 h-1.5 rounded-full mr-1 align-middle", TONE_DOT_CLASSES[tone])} />
        {format(start, "HH:mm")} {event.title}
      </span>
      {!compact && <span className="block truncate text-muted-foreground">até {format(end, "HH:mm")}{event.meet_link ? " · Meet" : event.location ? ` · ${event.location}` : ""}</span>}
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

  return (
    <div className="overflow-x-auto">
      <div className={cn(!single && "min-w-[760px]")}>
        <div className="flex border-b border-border/50 sticky top-0 bg-card z-20">
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
                {eventsOf(day).map((event) => {
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
              <div className="space-y-1.5">{items.map((e) => <div key={e.id} className="h-12"><EventBlock event={e} onOpen={onOpen} /></div>)}</div>
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
                    className="w-full flex items-center gap-1 text-[11px] text-left truncate rounded px-1 hover:bg-muted">
                    <span className={cn("w-1.5 h-1.5 rounded-full shrink-0", TONE_DOT_CLASSES[toneOf(e)])} />
                    <span className="tabular-nums text-muted-foreground">{format(toDate(e.start), "HH:mm")}</span>
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
                <TableCell className="tabular-nums">{format(start, "HH:mm")}–{format(toDate(event.end), "HH:mm")}</TableCell>
                <TableCell className="font-medium text-foreground">{event.title}</TableCell>
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

  const cancel = async (event: AgendaEvent) => {
    if (!window.confirm(`Cancelar "${event.title}"? O horário fica livre de novo.`)) return;
    try {
      await api.delete(`/agenda/events/${event.id}/`);
      toast.success("Evento cancelado.");
      setSelected(null);
      queryClient.invalidateQueries({ queryKey: ["agenda"] });
    } catch (error) {
      toast.error(errorDetail(error, "Não foi possível cancelar."));
    }
  };

  const sorted = useMemo(() => [...events].sort((a, b) => toDate(a.start).getTime() - toDate(b.start).getTime()), [events]);
  const eventsOf = (day: Date) => sorted.filter((e) => isSameDay(toDate(e.start), day));
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

      <ScheduleDialog open={scheduleOpen} onClose={closeSchedule} leadId={leadId} initial={slot} />
      <EventDetailsDialog event={selected} onClose={() => setSelected(null)} onCancel={cancel} />
    </PageShell>
  );
}
