export const LEAD_STATUS_LABELS: Record<string, string> = {
  ANALYSIS: "Análise",
  BUDGET: "Orçamento",
  NEGOTIATING: "Negociando",
  WON: "Venda",
  LOST: "Perdido",
};

export const LEAD_STATUS_STYLES: Record<string, string> = {
  ANALYSIS: "bg-slate-500/10 text-slate-600 border-slate-500/20",
  BUDGET: "bg-amber-500/10 text-amber-600 border-amber-500/20",
  NEGOTIATING: "bg-sky-500/10 text-sky-600 border-sky-500/20",
  WON: "bg-emerald-500/10 text-emerald-600 border-emerald-500/20",
  LOST: "bg-rose-500/10 text-rose-600 border-rose-500/20",
};

export const LEAD_STATUS_OPTIONS = [
  "ANALYSIS",
  "BUDGET",
  "NEGOTIATING",
  "WON",
  "LOST",
] as const;

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
