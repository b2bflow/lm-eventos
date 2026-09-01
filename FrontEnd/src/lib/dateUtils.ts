import { format, isValid, parseISO, Locale } from "date-fns";
import { ptBR } from "date-fns/locale";

/**
 * Converte com segurança qualquer formato de data (incluindo formatos aceitos no Chrome mas rejeitados no Safari)
 * para um objeto Date válido. Retorna null se for inválido.
 */
export function parseSafeDate(input: string | number | Date | null | undefined): Date | null {
  if (!input) return null;

  if (input instanceof Date) {
    return isValid(input) && !isNaN(input.getTime()) ? input : null;
  }

  if (typeof input === "number") {
    const d = new Date(input);
    return isValid(d) && !isNaN(d.getTime()) ? d : null;
  }

  if (typeof input === "string") {
    const trimmed = input.trim();
    if (!trimmed) return null;

    // Normaliza formatos com espaço tipo "YYYY-MM-DD HH:mm:ss" para ISO "YYYY-MM-DDTHH:mm:ss" (compatibilidade Safari)
    const normalized = trimmed.includes(" ") && !trimmed.includes("T")
      ? trimmed.replace(" ", "T")
      : trimmed;

    // Tenta parseISO primeiro
    try {
      const isoParsed = parseISO(normalized);
      if (isValid(isoParsed) && !isNaN(isoParsed.getTime())) {
        return isoParsed;
      }
    } catch {
      // continua para fallback nativo
    }

    // Tenta new Date padrão
    try {
      const nativeParsed = new Date(normalized);
      if (isValid(nativeParsed) && !isNaN(nativeParsed.getTime())) {
        return nativeParsed;
      }
    } catch {
      return null;
    }
  }

  return null;
}

/**
 * Formata uma data de forma segura, sem disparar exceção RangeError no date-fns
 * caso a data seja inválida ou venha em formato não suportado.
 */
export function formatSafeDate(
  input: string | number | Date | null | undefined,
  formatStr: string,
  options?: { locale?: Locale; fallback?: string }
): string {
  const fallback = options?.fallback ?? "";
  const date = parseSafeDate(input);

  if (!date) return fallback;

  try {
    return format(date, formatStr, { locale: options?.locale ?? ptBR });
  } catch (err) {
    console.warn("[formatSafeDate] Erro ao formatar data:", input, err);
    return fallback;
  }
}

/**
 * Retorna hora formatada no padrão 2 dígitos (HH:mm) de forma resiliente.
 */
export function formatSafeTime(
  input: string | number | Date | null | undefined,
  fallback = ""
): string {
  const date = parseSafeDate(input);
  if (!date) return fallback;

  try {
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return fallback;
  }
}
