import { AlertTriangle, Info, Lock, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatBRL } from "@/lib/format";
import type { QuoteResult } from "@/hooks/useSales";

const BLOCK_LABELS: Record<string, string> = {
  estrutura: "Estrutura",
  som: "Som",
  iluminacao: "Iluminação",
  video: "Vídeo",
  palco: "Palco e praticáveis",
  equipe: "Equipe",
  outros: "Outros",
};

function qty(value: number) {
  return Number.isInteger(value) ? String(value) : value.toLocaleString("pt-BR");
}

export function QuoteSummary({ result, loading, error }: { result?: QuoteResult; loading: boolean; error?: string | null }) {
  if (error) {
    return <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-700">{error}</div>;
  }
  if (!result) {
    return (
      <div className="rounded-2xl border border-dashed border-border p-6 text-sm text-muted-foreground text-center">
        {loading ? <Loader2 className="w-5 h-5 animate-spin mx-auto" /> : "Preencha os dados para ver o valor."}
      </div>
    );
  }

  const blocks = Array.from(new Set(result.lines.map((l) => l.block)));

  return (
    <div className={cn("glass rounded-2xl border border-border/50 p-4 space-y-4 transition-opacity", loading && "opacity-60")}>
      {result.lock_reasons.length > 0 && (
        <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm space-y-1">
          <p className="font-semibold flex items-center gap-2 text-amber-800 dark:text-amber-300">
            <Lock className="w-4 h-4" /> {result.requires_meeting ? "Vira reunião com a Erica" : "Vai para aprovação da Erica"}
          </p>
          <ul className="list-disc pl-5 text-amber-800 dark:text-amber-300">
            {result.lock_reasons.map((r, i) => <li key={i}>{r.message}{r.detail ? `: ${r.detail}` : ""}</li>)}
          </ul>
        </div>
      )}

      {blocks.map((block) => (
        <div key={block} className="space-y-1">
          <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">{BLOCK_LABELS[block] || block}</h4>
          <ul className="space-y-1">
            {result.lines.filter((l) => l.block === block).map((line, idx) => (
              <li key={`${line.code}-${idx}`} className={cn("text-sm flex items-start justify-between gap-3 rounded px-1", line.shortage && "bg-rose-500/10 text-rose-700")}>
                <span className="min-w-0">
                  {qty(line.qty)} {line.unit} · {line.name}
                  {line.note && <span className="text-xs text-muted-foreground"> ({line.note})</span>}
                  {line.shortage && (
                    <span className="flex items-center gap-1 text-xs font-semibold">
                      <AlertTriangle className="w-3 h-3" /> Estoque insuficiente: disponível {line.available}
                    </span>
                  )}
                </span>
                <span className="shrink-0 tabular-nums">{line.unit_price === null ? "sem preço" : formatBRL(line.subtotal)}</span>
              </li>
            ))}
          </ul>
        </div>
      ))}

      {result.operational.length > 0 && (
        <div className="space-y-1">
          <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Custos operacionais</h4>
          <ul className="space-y-1">
            {result.operational.map((c) => (
              <li key={c.code} className="text-sm flex justify-between gap-3"><span>{c.name}</span><span className="tabular-nums">{formatBRL(c.subtotal)}</span></li>
            ))}
          </ul>
        </div>
      )}

      <div className="border-t pt-3 space-y-1 text-sm">
        <div className="flex justify-between"><span>Itens</span><span className="tabular-nums">{formatBRL(result.items_total)}</span></div>
        {result.costs_total > 0 && <div className="flex justify-between"><span>Custos operacionais</span><span className="tabular-nums">{formatBRL(result.costs_total)}</span></div>}
        {result.margin_pct > 0 && <div className="flex justify-between"><span>Margem ({Math.round(result.margin_pct * 100)}%)</span><span className="tabular-nums">{formatBRL(result.margin_value)}</span></div>}
        {result.with_invoice && <div className="flex justify-between"><span>Nota fiscal</span><span className="tabular-nums">{formatBRL(result.invoice_value)}</span></div>}
        {result.discount > 0 && <div className="flex justify-between text-rose-600"><span>Desconto</span><span className="tabular-nums">-{formatBRL(result.discount)}</span></div>}
        {result.manual_adjustment !== 0 && <div className="flex justify-between"><span>Ajuste manual</span><span className="tabular-nums">{formatBRL(result.manual_adjustment)}</span></div>}
        {result.periods > 1 && <div className="flex justify-between text-amber-700"><span>Períodos de locação</span><span>{result.periods} semanas</span></div>}
        <div className="flex justify-between text-lg font-bold pt-1"><span>Total</span><span className="tabular-nums">{formatBRL(result.total)}</span></div>
      </div>

      {result.warnings.length > 0 && (
        <ul className="text-xs text-muted-foreground space-y-1">
          {Array.from(new Set(result.warnings)).map((w) => (
            <li key={w} className="flex items-start gap-1.5"><Info className="w-3.5 h-3.5 mt-0.5 shrink-0" />{w}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
