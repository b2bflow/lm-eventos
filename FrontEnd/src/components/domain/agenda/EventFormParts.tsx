import { useState } from "react";
import { format } from "date-fns";
import { ptBR } from "date-fns/locale";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Select, SelectContent, SelectItem, SelectSeparator, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import {
  WEEK_ORDER, WEEKDAY_LETTERS, WEEKDAY_NAMES, dayToDate, describeRule, presetOf, presetOptions, presetRule, pyWeekday,
  type RecurrencePreset, type RecurrenceRule,
} from "./recurrence";

export type Scope = "this" | "following" | "all";

// --- Data e hora -------------------------------------------------------------------------------

/** Botão de data com calendário, como o "qua., 28 de out. de 2026" do Google Agenda. */
export function DateField({ value, onChange, label }: { value: string; onChange: (day: string) => void; label: string }) {
  const [open, setOpen] = useState(false);
  const date = dayToDate(value);
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button type="button" variant="ghost" aria-label={label}
          className="h-9 px-2.5 bg-secondary/50 hover:bg-secondary font-normal text-foreground">
          {`${format(date, "EEEE", { locale: ptBR }).slice(0, 3)}., ${format(date, "d 'de' MMM'.' 'de' yyyy", { locale: ptBR })}`}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-0" align="start">
        <Calendar mode="single" locale={ptBR} selected={date} defaultMonth={date}
          onSelect={(picked) => { if (picked) { onChange(format(picked, "yyyy-MM-dd")); setOpen(false); } }} />
      </PopoverContent>
    </Popover>
  );
}

const QUARTERS = Array.from({ length: 96 }, (_, i) => `${String(Math.floor(i / 4)).padStart(2, "0")}:${String((i % 4) * 15).padStart(2, "0")}`);
const minutesOf = (hhmm: string) => Number(hhmm.slice(0, 2)) * 60 + Number(hhmm.slice(3, 5));

function durationLabel(minutes: number) {
  if (minutes < 60) return `${minutes} min`;
  const hours = minutes / 60;
  return `${Number.isInteger(hours) ? hours : hours.toFixed(1).replace(".", ",")} h`;
}

/** Hora de 15 em 15 minutos. No fim, com a duração ao lado ("13:00 (1 h)"), como no Google. */
export function TimeSelect({ value, onChange, after, label }: {
  value: string; onChange: (time: string) => void; after?: string; label: string;
}) {
  const options = (QUARTERS.includes(value) ? QUARTERS : [...QUARTERS, value].sort())
    .filter((t) => after === undefined || minutesOf(t) > minutesOf(after));
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger aria-label={label} className="h-9 w-auto gap-1 border-0 bg-secondary/50 hover:bg-secondary px-2.5 tabular-nums">
        <SelectValue />
      </SelectTrigger>
      <SelectContent className="max-h-72">
        {options.map((t) => (
          <SelectItem key={t} value={t} className="tabular-nums">
            {t}{after !== undefined && <span className="text-muted-foreground"> ({durationLabel(minutesOf(t) - minutesOf(after))})</span>}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

// --- Repetição ---------------------------------------------------------------------------------

/** Seletor "Não se repete" do Google: opções rápidas pela data de início e "Personalizar...". */
export function RecurrenceSelect({ rule, start, onChange }: {
  rule: RecurrenceRule | null; start: Date; onChange: (rule: RecurrenceRule | null) => void;
}) {
  const [customOpen, setCustomOpen] = useState(false);
  const preset = presetOf(rule, start);
  return (
    <>
      <Select value={preset} onValueChange={(value) => {
        if (value === "open-custom") setCustomOpen(true);
        else if (value !== "custom") onChange(presetRule(value as RecurrencePreset, start));
      }}>
        <SelectTrigger aria-label="Repetição" className="h-9 w-auto max-w-full gap-1 border-0 bg-secondary/50 hover:bg-secondary px-2.5">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {preset === "custom" && <SelectItem value="custom">{describeRule(rule, start)}</SelectItem>}
          {presetOptions(start).map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
          <SelectSeparator />
          <SelectItem value="open-custom">Personalizar...</SelectItem>
        </SelectContent>
      </Select>
      {customOpen && (
        <CustomRecurrenceDialog start={start} initial={rule} onClose={() => setCustomOpen(false)}
          onDone={(next) => { onChange(next); setCustomOpen(false); }} />
      )}
    </>
  );
}

const UNIT_LABELS: Record<RecurrenceRule["freq"], [string, string]> = {
  daily: ["dia", "dias"], weekly: ["semana", "semanas"], monthly: ["mês", "meses"], yearly: ["ano", "anos"],
};

/** "Recorrência personalizada" do Google: a cada N, dias da semana, forma mensal e quando termina. */
function CustomRecurrenceDialog({ start, initial, onClose, onDone }: {
  start: Date; initial: RecurrenceRule | null; onClose: () => void; onDone: (rule: RecurrenceRule) => void;
}) {
  const weekday = pyWeekday(start);
  const nth = Math.floor((start.getDate() - 1) / 7) + 1;
  const lastWeek = start.getDate() + 7 > new Date(start.getFullYear(), start.getMonth() + 1, 0).getDate();
  const [freq, setFreq] = useState<RecurrenceRule["freq"]>(initial?.freq ?? "weekly");
  const [every, setEvery] = useState(initial?.interval ?? 1);
  const [days, setDays] = useState<number[]>(initial?.by_weekday?.length ? initial.by_weekday : [weekday]);
  const [monthly, setMonthly] = useState<NonNullable<RecurrenceRule["monthly"]>>(initial?.monthly ?? "day");
  const [ends, setEnds] = useState<"never" | "until" | "count">(initial?.until ? "until" : initial?.count ? "count" : "never");
  const [until, setUntil] = useState(initial?.until ?? format(new Date(start.getFullYear(), start.getMonth() + 3, start.getDate()), "yyyy-MM-dd"));
  const [count, setCount] = useState(initial?.count ?? 13);

  const toggleDay = (day: number) => setDays((current) =>
    current.includes(day) ? (current.length > 1 ? current.filter((d) => d !== day) : current) : [...current, day]);

  const done = () => onDone({
    freq, interval: Math.max(1, every),
    ...(freq === "weekly" ? { by_weekday: [...days].sort() } : {}),
    ...(freq === "monthly" ? { monthly } : {}),
    until: ends === "until" ? until : null,
    count: ends === "count" ? Math.max(1, count) : null,
  });

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader><DialogTitle>Recorrência personalizada</DialogTitle></DialogHeader>
        <div className="space-y-5 text-sm">
          <div className="flex items-center gap-2">
            <span>Repetir a cada</span>
            <Input type="number" min={1} max={99} value={every} aria-label="Intervalo"
              onChange={(e) => setEvery(Number(e.target.value) || 1)} className="h-9 w-16 bg-secondary/50 border-0" />
            <Select value={freq} onValueChange={(v) => setFreq(v as RecurrenceRule["freq"])}>
              <SelectTrigger aria-label="Unidade" className="h-9 w-auto border-0 bg-secondary/50"><SelectValue /></SelectTrigger>
              <SelectContent>
                {(Object.keys(UNIT_LABELS) as RecurrenceRule["freq"][]).map((f) => (
                  <SelectItem key={f} value={f}>{UNIT_LABELS[f][every === 1 ? 0 : 1]}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {freq === "weekly" && (
            <div className="space-y-2">
              <p>Repetir:</p>
              <div className="flex gap-1.5">
                {WEEK_ORDER.map((d) => (
                  <button key={d} type="button" onClick={() => toggleDay(d)} title={WEEKDAY_NAMES[d]} aria-pressed={days.includes(d)}
                    className={cn("w-8 h-8 rounded-full text-xs font-semibold transition-colors",
                      days.includes(d) ? "bg-primary text-primary-foreground" : "bg-secondary text-muted-foreground hover:bg-secondary/70")}>
                    {WEEKDAY_LETTERS[d]}
                  </button>
                ))}
              </div>
            </div>
          )}

          {freq === "monthly" && (
            <Select value={monthly} onValueChange={(v) => setMonthly(v as NonNullable<RecurrenceRule["monthly"]>)}>
              <SelectTrigger aria-label="Dia do mês" className="h-9 w-auto border-0 bg-secondary/50"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="day">Mensal no dia {start.getDate()}</SelectItem>
                {nth <= 4 && <SelectItem value="weekday">{describeRule({ freq: "monthly", monthly: "weekday" }, start)}</SelectItem>}
                {lastWeek && <SelectItem value="last_weekday">{describeRule({ freq: "monthly", monthly: "last_weekday" }, start)}</SelectItem>}
              </SelectContent>
            </Select>
          )}

          <fieldset className="space-y-2.5">
            <legend className="mb-2">Termina em</legend>
            <label className="flex items-center gap-3 cursor-pointer">
              <input type="radio" name="ends" checked={ends === "never"} onChange={() => setEnds("never")} className="accent-primary w-4 h-4" />
              Nunca
            </label>
            <label className="flex items-center gap-3 cursor-pointer">
              <input type="radio" name="ends" checked={ends === "until"} onChange={() => setEnds("until")} className="accent-primary w-4 h-4" />
              <span className="w-12">Em</span>
              <Input type="date" value={until} min={format(start, "yyyy-MM-dd")} disabled={ends !== "until"} aria-label="Termina em"
                onChange={(e) => setUntil(e.target.value)} className="h-9 w-auto bg-secondary/50 border-0" />
            </label>
            <label className="flex items-center gap-3 cursor-pointer">
              <input type="radio" name="ends" checked={ends === "count"} onChange={() => setEnds("count")} className="accent-primary w-4 h-4" />
              <span className="w-12">Após</span>
              <Input type="number" min={1} max={730} value={count} disabled={ends !== "count"} aria-label="Ocorrências"
                onChange={(e) => setCount(Number(e.target.value) || 1)} className="h-9 w-20 bg-secondary/50 border-0" />
              <span className={cn(ends !== "count" && "text-muted-foreground")}>ocorrências</span>
            </label>
          </fieldset>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>Cancelar</Button>
          <Button onClick={done}>Concluído</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// --- Alcance numa série ------------------------------------------------------------------------

/** "Editar evento recorrente" / "Excluir evento recorrente": este, este e os seguintes, todos. */
export function ScopeDialog({ action, allowThis = true, onConfirm, onClose }: {
  action: "edit" | "delete"; allowThis?: boolean; onConfirm: (scope: Scope) => void; onClose: () => void;
}) {
  const [scope, setScope] = useState<Scope>(allowThis ? "this" : "following");
  const options: [Scope, string][] = [
    ...(allowThis ? [["this", "Este evento"] as [Scope, string]] : []),
    ["following", "Este e os seguintes"],
    ["all", "Todos os eventos"],
  ];
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-xs">
        <DialogHeader>
          <DialogTitle>{action === "edit" ? "Editar evento recorrente" : "Excluir evento recorrente"}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3 text-sm">
          {options.map(([value, label]) => (
            <label key={value} className="flex items-center gap-3 cursor-pointer">
              <input type="radio" name="scope" checked={scope === value} onChange={() => setScope(value)} className="accent-primary w-4 h-4" />
              {label}
            </label>
          ))}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>Cancelar</Button>
          <Button variant={action === "delete" ? "destructive" : "default"} onClick={() => onConfirm(scope)}>OK</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
