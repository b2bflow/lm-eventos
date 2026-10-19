// Tons de status compartilhados por StatusBadge, KpiCard e o que os módulos precisarem colorir.
export type Tone = "success" | "warning" | "danger" | "info" | "ai" | "neutral" | "primary";

// Fundo, texto e borda de cada tom, no mesmo padrão dos badges que o core já usa.
export const TONE_CLASSES: Record<Tone, string> = {
  success: "bg-emerald-500/10 text-emerald-600 border-emerald-500/20 dark:text-emerald-400",
  warning: "bg-amber-500/10 text-amber-600 border-amber-500/20 dark:text-amber-400",
  danger: "bg-red-500/10 text-red-600 border-red-500/20 dark:text-red-400",
  info: "bg-sky-500/10 text-sky-600 border-sky-500/20 dark:text-sky-400",
  ai: "bg-violet-500/10 text-violet-600 border-violet-500/20 dark:text-violet-400",
  neutral: "bg-muted text-muted-foreground border-border",
  primary: "bg-primary/10 text-primary border-primary/20",
};

// Cor sólida do tom, para pontos e legendas.
export const TONE_DOT_CLASSES: Record<Tone, string> = {
  success: "bg-emerald-500",
  warning: "bg-amber-500",
  danger: "bg-red-500",
  info: "bg-sky-500",
  ai: "bg-violet-500",
  neutral: "bg-muted-foreground",
  primary: "bg-primary",
};
