import { format, isPast } from "date-fns";
import { ptBR } from "date-fns/locale";

const brl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

/** 12680 -> "R$ 12.680,00" */
export function formatBRL(value?: number | null): string {
  return brl.format(value ?? 0).replace(/[\u00a0\u202f]/g, " ");
}

export function formatDate(value?: string | null): string {
  if (!value) return "";
  return format(new Date(value), "dd/MM/yyyy", { locale: ptBR });
}

/** Datas de evento são gravadas como dia (00:00 UTC): exibe sem converter fuso. */
export function formatDay(value?: string | null): string {
  if (!value) return "";
  const [y, m, d] = value.slice(0, 10).split("-");
  return `${d}/${m}/${y}`;
}

export function formatDateTime(value?: string | null): string {
  if (!value) return "";
  return format(new Date(utcIso(value)), "dd/MM HH:mm", { locale: ptBR });
}

export function isOverdue(value?: string | null): boolean {
  return !!value && isPast(new Date(utcIso(value)));
}

/** O backend devolve datas UTC sem fuso ("2026-10-16T13:00:00"); marca como UTC. */
export function utcIso(value: string): string {
  return /[zZ]|[+-]\d{2}:?\d{2}$/.test(value) ? value : `${value}Z`;
}

export function phoneDisplay(phone?: string | null): string {
  const digits = (phone || "").replace(/\D/g, "");
  if (digits.length === 13 && digits.startsWith("55")) {
    return `(${digits.slice(2, 4)}) ${digits.slice(4, 9)}-${digits.slice(9)}`;
  }
  return phone || "";
}
