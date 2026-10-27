import { format } from "date-fns";
import { ptBR } from "date-fns/locale";

/** Regra de repetição (mesmo formato do backend, agenda/services/recurrence.py). Dias: Seg=0 ... Dom=6. */
export interface RecurrenceRule {
  freq: "daily" | "weekly" | "monthly" | "yearly";
  interval?: number;
  by_weekday?: number[];
  monthly?: "day" | "weekday" | "last_weekday";
  until?: string | null;
  count?: number | null;
}

export type RecurrencePreset = "none" | "daily" | "weekly" | "monthly" | "monthly_last" | "yearly" | "weekdays" | "custom";

export const WEEKDAY_NAMES = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"];
/** Ordem do Google em português: começa no domingo. Valor = índice do backend. */
export const WEEK_ORDER = [6, 0, 1, 2, 3, 4, 5];
export const WEEKDAY_LETTERS: Record<number, string> = { 6: "D", 0: "S", 1: "T", 2: "Q", 3: "Q", 4: "S", 5: "S" };
const ORDINALS = ["primeira", "segunda", "terceira", "quarta", "quinta"];
const WORKDAYS = [0, 1, 2, 3, 4];

/** Dia da semana no padrão do backend (Seg=0). */
export const pyWeekday = (date: Date) => (date.getDay() + 6) % 7;
const nthWeekday = (date: Date) => Math.floor((date.getDate() - 1) / 7) + 1;
const isLastWeekOfMonth = (date: Date) => date.getDate() + 7 > new Date(date.getFullYear(), date.getMonth() + 1, 0).getDate();
const sameDays = (a: number[] = [], b: number[]) => a.length === b.length && [...a].sort().every((d, i) => d === [...b].sort()[i]);

/** Regra de cada opção rápida, calculada a partir da data de início (como o Google faz). */
export function presetRule(preset: RecurrencePreset, start: Date): RecurrenceRule | null {
  switch (preset) {
    case "daily": return { freq: "daily", interval: 1 };
    case "weekly": return { freq: "weekly", interval: 1, by_weekday: [pyWeekday(start)] };
    case "weekdays": return { freq: "weekly", interval: 1, by_weekday: WORKDAYS };
    case "monthly": return { freq: "monthly", interval: 1, monthly: "weekday" };
    case "monthly_last": return { freq: "monthly", interval: 1, monthly: "last_weekday" };
    case "yearly": return { freq: "yearly", interval: 1 };
    default: return null;
  }
}

/** Qual opção rápida corresponde à regra ("custom" quando nenhuma). */
export function presetOf(rule: RecurrenceRule | null, start: Date): RecurrencePreset {
  if (!rule) return "none";
  if ((rule.interval ?? 1) !== 1 || rule.until || rule.count) return "custom";
  if (rule.freq === "daily") return "daily";
  if (rule.freq === "yearly") return "yearly";
  if (rule.freq === "weekly") {
    if (sameDays(rule.by_weekday, [pyWeekday(start)])) return "weekly";
    if (sameDays(rule.by_weekday, WORKDAYS)) return "weekdays";
    return "custom";
  }
  if (rule.monthly === "weekday" && nthWeekday(start) <= 4) return "monthly";
  if (rule.monthly === "last_weekday") return "monthly_last";
  return "custom";
}

/** Opções do seletor "Não se repete" na ordem do Google. */
export function presetOptions(start: Date): { value: RecurrencePreset; label: string }[] {
  const weekday = WEEKDAY_NAMES[pyWeekday(start)];
  const options: { value: RecurrencePreset; label: string }[] = [
    { value: "none", label: "Não se repete" },
    { value: "daily", label: "Todos os dias" },
    { value: "weekly", label: `Semanal: cada ${weekday}` },
  ];
  if (nthWeekday(start) <= 4) options.push({ value: "monthly", label: `Mensal no(a) ${ORDINALS[nthWeekday(start) - 1]} ${weekday}` });
  if (isLastWeekOfMonth(start)) options.push({ value: "monthly_last", label: `Mensal no(a) última ${weekday}` });
  options.push(
    { value: "yearly", label: `Anual em ${format(start, "d 'de' MMMM", { locale: ptBR })}` },
    { value: "weekdays", label: "Todos os dias da semana (segunda a sexta-feira)" },
  );
  return options;
}

function joinPt(items: string[]) {
  return items.length <= 1 ? items.join("") : `${items.slice(0, -1).join(", ")} e ${items[items.length - 1]}`;
}

/** Texto da regra, como o Google mostra no evento ("Semanal: cada quarta-feira, 10 vezes"). */
export function describeRule(rule: RecurrenceRule | null | undefined, start: Date): string {
  if (!rule) return "Não se repete";
  const n = rule.interval ?? 1;
  const weekday = WEEKDAY_NAMES[pyWeekday(start)];
  let text: string;
  if (rule.freq === "daily") {
    text = n === 1 ? "Todos os dias" : `A cada ${n} dias`;
  } else if (rule.freq === "weekly") {
    const days = rule.by_weekday?.length ? rule.by_weekday : [pyWeekday(start)];
    if (n === 1 && sameDays(days, WORKDAYS)) text = "Todos os dias da semana (segunda a sexta-feira)";
    else {
      const names = joinPt(WEEK_ORDER.filter((d) => days.includes(d)).map((d) => WEEKDAY_NAMES[d]));
      text = n === 1 ? `Semanal: cada ${names}` : `A cada ${n} semanas: ${names}`;
    }
  } else if (rule.freq === "monthly") {
    const which = rule.monthly === "weekday" ? `no(a) ${ORDINALS[Math.min(nthWeekday(start), 5) - 1]} ${weekday}`
      : rule.monthly === "last_weekday" ? `no(a) última ${weekday}` : `no dia ${start.getDate()}`;
    text = n === 1 ? `Mensal ${which}` : `A cada ${n} meses ${which}`;
  } else {
    const day = format(start, "d 'de' MMMM", { locale: ptBR });
    text = n === 1 ? `Anual em ${day}` : `A cada ${n} anos em ${day}`;
  }
  if (rule.until) text += `, até ${format(new Date(`${rule.until}T12:00:00`), "d 'de' MMM 'de' yyyy", { locale: ptBR })}`;
  if (rule.count) text += rule.count === 1 ? ", 1 vez" : `, ${rule.count} vezes`;
  return text;
}

/** Ao mudar a data de início, "Semanal: cada <dia>" acompanha o novo dia (como no Google). */
export function followStart(rule: RecurrenceRule | null, before: Date, after: Date): RecurrenceRule | null {
  if (rule?.freq === "weekly" && sameDays(rule.by_weekday, [pyWeekday(before)])) {
    return { ...rule, by_weekday: [pyWeekday(after)] };
  }
  return rule;
}

export const sameRule = (a: RecurrenceRule | null | undefined, b: RecurrenceRule | null | undefined) => {
  if (!a || !b) return !a && !b;
  return a.freq === b.freq && (a.interval ?? 1) === (b.interval ?? 1) && (a.until ?? null) === (b.until ?? null)
    && (a.count ?? null) === (b.count ?? null) && (a.freq !== "weekly" || sameDays(a.by_weekday, b.by_weekday ?? []))
    && (a.freq !== "monthly" || (a.monthly ?? "day") === (b.monthly ?? "day"));
};

/** "yyyy-MM-dd" -> Date local ao meio-dia (não vira o dia anterior em fuso nenhum). */
export const dayToDate = (day: string) => new Date(`${day}T12:00:00`);
