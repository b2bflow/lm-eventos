import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { TONE_CLASSES, TONE_DOT_CLASSES, type Tone } from "@/lib/tones";

interface StatusBadgeProps {
  tone?: Tone;
  children: ReactNode;
  dot?: boolean;
  className?: string;
}

// Selo de status (agendado, confirmado, faltou...): ponto colorido, rótulo e fundo do tom.
export function StatusBadge({ tone = "neutral", children, dot = true, className }: StatusBadgeProps) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium whitespace-nowrap", TONE_CLASSES[tone], className)}>
      {dot && <span className={cn("w-1.5 h-1.5 rounded-full", TONE_DOT_CLASSES[tone])} aria-hidden />}
      {children}
    </span>
  );
}
