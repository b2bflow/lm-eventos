import { useQuery } from "@tanstack/react-query";
import api from "@/services/api";

export interface QuickReply {
  product: string; // "geral" ou um produto do funil
  title: string;
  text: string;
}

export interface LmSettingsData {
  sdr_name?: string;
  quick_replies?: QuickReply[];
  [key: string]: unknown;
}

/** Configuração da operação LM (GET /crm/settings/, qualquer usuário autenticado). */
export function useLmSettings() {
  return useQuery({
    queryKey: ["lm-settings"],
    queryFn: async () => (await api.get<LmSettingsData>("/crm/settings/")).data,
    staleTime: 5 * 60 * 1000,
  });
}

/** Respostas rápidas do produto do cliente (mais as gerais), com {nome} e {sdr} preenchidos
 * ({sdr} = quem está enviando; sem nome no perfil, o nome da SDR nas configurações). */
export function quickRepliesFor(
  settings: LmSettingsData | undefined, product: string | null | undefined, customerName: string | undefined, sdrName: string,
): QuickReply[] {
  const first = (customerName || "").trim().split(/\s+/)[0] || "";
  const name = first && !first.startsWith("WhatsApp") && !/^\d+$/.test(first) ? first : "";
  return (settings?.quick_replies ?? [])
    .filter((r) => r.product === "geral" || r.product === product)
    .map((r) => ({
      ...r,
      text: r.text
        .replace(/\{nome\}/g, name)
        .replace(/\{sdr\}/g, sdrName || "a equipe comercial")
        .replace(/Olá, \./g, "Olá.")
        .replace(/\s{2,}/g, " "),
    }));
}
