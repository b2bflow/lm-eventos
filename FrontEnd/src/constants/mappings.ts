import type { Tone } from "@/lib/tones";
// Etapas do funil (espelho de BackEnd/crm/domain.py)
export const LEAD_STATUS_OPTIONS = [
  "NEW_LEAD",
  "QUALIFIED",
  "PROPOSAL_SENT",
  "PROPOSAL_ACCEPTED",
  "CONTRACT_SIGNED",
  "LOST",
] as const;

export type LeadStage = (typeof LEAD_STATUS_OPTIONS)[number];

export const LEAD_STATUS_LABELS: Record<string, string> = {
  NEW_LEAD: "Novo lead",
  QUALIFIED: "Lead qualificado",
  PROPOSAL_SENT: "Proposta enviada",
  PROPOSAL_ACCEPTED: "Proposta aceita",
  CONTRACT_SIGNED: "Contrato assinado",
  // Status das cotações (tela /leads, coleção quotes)
  ANALYSIS: "Análise",
  BUDGET: "Orçamento Enviado",
  WAITING_BUDGET: "Orçamento Pendente",
  NEGOTIATING: "Negociando",
  WON: "Venda",
  LOST: "Perdido",
};

export const LEAD_STATUS_STYLES: Record<string, string> = {
  NEW_LEAD: "bg-slate-500/10 text-slate-600 border-slate-500/20",
  QUALIFIED: "bg-violet-500/10 text-violet-600 border-violet-500/20",
  PROPOSAL_SENT: "bg-amber-500/10 text-amber-600 border-amber-500/20",
  PROPOSAL_ACCEPTED: "bg-sky-500/10 text-sky-600 border-sky-500/20",
  CONTRACT_SIGNED: "bg-emerald-500/10 text-emerald-600 border-emerald-500/20",
  LOST: "bg-rose-500/10 text-rose-600 border-rose-500/20",
  ANALYSIS: "bg-slate-500/10 text-slate-600 border-slate-500/20",
  BUDGET: "bg-amber-500/10 text-amber-600 border-amber-500/20",
  WAITING_BUDGET: "bg-yellow-500/10 text-yellow-600 border-yellow-500/20",
  NEGOTIATING: "bg-sky-500/10 text-sky-600 border-sky-500/20",
  WON: "bg-emerald-500/10 text-emerald-600 border-emerald-500/20",
};

// Cores sólidas (selos na lista de conversas)
// Status das cotações (tela /leads)
export const QUOTE_STATUS_OPTIONS = [
  "ANALYSIS",
  "WAITING_BUDGET",
  "BUDGET",
  "NEGOTIATING",
  "WON",
  "LOST",
] as const;

export const LEAD_STATUS_SOLID: Record<string, string> = {
  NEW_LEAD: "bg-slate-600 text-white border-slate-500",
  QUALIFIED: "bg-violet-600 text-white border-violet-500",
  PROPOSAL_SENT: "bg-amber-500 text-white border-amber-400",
  PROPOSAL_ACCEPTED: "bg-sky-500 text-white border-sky-400",
  CONTRACT_SIGNED: "bg-emerald-500 text-white border-emerald-400",
  LOST: "bg-rose-500 text-white border-rose-400",
};

// Registros ainda não migrados pelo migrate_lm_stages
const LEGACY_STAGE_MAP: Record<string, LeadStage> = {
  ANALYSIS: "NEW_LEAD",
  WAITING_BUDGET: "QUALIFIED",
  BUDGET: "QUALIFIED",
  NEGOTIATING: "PROPOSAL_SENT",
  WON: "CONTRACT_SIGNED",
};

export function resolveStage(stage?: string | null): LeadStage {
  if (stage && (LEAD_STATUS_OPTIONS as readonly string[]).includes(stage)) return stage as LeadStage;
  return (stage && LEGACY_STAGE_MAP[stage]) || "NEW_LEAD";
}

export const LOST_REASON_LABELS: Record<string, string> = {
  preco: "Preço",
  data_indisponivel: "Data indisponível",
  sem_resposta: "Sem resposta",
  fechou_com_outro: "Fechou com outro",
  desistiu: "Desistiu",
};

export const PRODUCT_LABELS: Record<string, string> = {
  estrutura_porta: "Estrutura (locação de porta)",
  estrutura_montagem: "Estrutura com montagem",
  corporativo: "Corporativo",
  social: "Social",
  produto_unico: "Produto único",
};

export const PROPOSAL_MODE_LABELS: Record<string, string> = {
  porta: "Locação de porta",
  corporativo: "Corporativo",
  social: "Social",
  produto_unico: "Produto único",
};

export const OWNER_LABELS: Record<string, string> = {
  sdr: "SDR",
  erica: "Erica",
  lucia: "Lúcia",
};

export const CONTACT_TYPE_LABELS: Record<string, string> = {
  lead: "Lead",
  cliente: "Cliente",
  parceiro: "Parceiro",
  fornecedor: "Fornecedor",
  candidato: "Candidato",
  outro: "Outro",
};

export const ORIGIN_LABELS: Record<string, string> = {
  anuncio_ctwa: "Anúncio (clique para WhatsApp)",
  instagram: "Instagram",
  google: "Google",
  indicacao: "Indicação",
  site: "Site",
  parceiro: "Parceiro",
};

export const FLAG_LABELS: Record<string, string> = {
  ligacao_pendente: "Ligação pendente",
  reuniao_agendada: "Reunião agendada",
  visita_agendada: "Visita agendada",
  aguardando_erica: "Aguardando Erica",
  aguardando_cliente: "Aguardando cliente",
  aguardando_aprovacao_desconto: "Aguardando aprovação",
};

export const CALL_OUTCOME_LABELS: Record<string, string> = {
  atendeu: "Atendeu",
  nao_atendeu: "Não atendeu",
  caixa_postal: "Caixa postal",
  numero_invalido: "Número inválido",
  remarcar: "Pediu para ligar depois",
};

export const CUSTOMER_TAG_LABELS: Record<string, string> = {
  "visita tecnica": "Visita técnica",
  "operador humano": "Operador humano",
  "orcamento": "Orçamento",
};

export const CUSTOMER_TAG_STYLES: Record<string, string> = {
  "visita tecnica": "bg-violet-500/10 text-violet-600 border-violet-500/20",
  "operador humano": "bg-blue-500/10 text-blue-600 border-blue-500/20",
  "orcamento": "bg-amber-500/10 text-amber-600 border-amber-500/20",
};

export const CUSTOMER_TAG_OPTIONS = ["visita tecnica", "operador humano", "orcamento"] as const;

// --- STATUS DE COLABORADOR ---
export const USER_STATUS_LABELS: Record<string, string> = {
  ONLINE: "Online",
  INATIVO: "Ausente",
  OFFLINE: "Offline",
};

export const USER_STATUS_COLORS: Record<string, string> = {
  ONLINE: "text-green-500",
  INATIVO: "text-yellow-500",
  OFFLINE: "text-muted-foreground",
};

export const CHAT_HANDOVER_MODES = {
  AGENTE: {
    key: "AGENTE",
    label: "Agente IA",
    color: "bg-purple-500",
    description: "IA respondendo"
  },
  OPERADOR: {
    key: "OPERADOR",
    label: "Operador",
    color: "bg-blue-600",
    description: "Humano no controle"
  }
};

/** Tom de cada etapa no padrão dos módulos (StatusBadge, ponto da coluna do quadro). */
export const LEAD_STAGE_TONES: Record<string, Tone> = {
  NEW_LEAD: "neutral",
  QUALIFIED: "ai",
  PROPOSAL_SENT: "warning",
  PROPOSAL_ACCEPTED: "info",
  CONTRACT_SIGNED: "success",
  LOST: "danger",
};
