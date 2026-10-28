import { useState } from "react";
import { AlertTriangle, Check, Info, Lock, Loader2, Pencil, RotateCcw, X } from "lucide-react";
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

/** Edição de valores da proposta: preço unitário por item e valor final. `null` volta ao calculado. */
export interface QuoteEditing {
  onPrice: (code: string, value: number | null) => void;
  onFinalTotal: (value: number | null) => void;
}

/** Campo de valor em linha: Enter salva, Esc cancela. */
function MoneyInput({ initial, onSave, onCancel, label }: {
  initial: number | null; onSave: (value: number) => void; onCancel: () => void; label: string;
}) {
  const [value, setValue] = useState(initial !== null ? String(initial) : "");
  const number = Number(value.replace(",", "."));
  const valid = value.trim() !== "" && Number.isFinite(number) && number >= 0;
  return (
    <span className="flex items-center gap-1">
      <span className="text-xs text-muted-foreground">R$</span>
      <input autoFocus type="number" min={0} step="0.01" value={value} aria-label={label}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && valid) onSave(number);
          if (e.key === "Escape") onCancel();
        }}
        className="w-24 h-7 rounded-md border border-border bg-background px-2 text-sm tabular-nums outline-none focus:ring-2 focus:ring-primary/30 [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none" />
      <button type="button" className="p-1 rounded text-emerald-600 hover:bg-emerald-500/10 disabled:opacity-30" disabled={!valid}
        onClick={() => onSave(number)} title="Salvar" aria-label="Salvar"><Check className="w-4 h-4" /></button>
      <button type="button" className="p-1 rounded text-muted-foreground hover:bg-muted" onClick={onCancel} title="Cancelar" aria-label="Cancelar">
        <X className="w-4 h-4" />
      </button>
    </span>
  );
}

export function QuoteSummary({ result, loading, error, editing }: {
  result?: QuoteResult; loading: boolean; error?: string | null; editing?: QuoteEditing;
}) {
  const [editingLine, setEditingLine] = useState<string | null>(null);
  const [editingTotal, setEditingTotal] = useState(false);

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
            {result.lines.filter((l) => l.block === block).map((line, idx) => {
              const key = `${block}-${line.code}-${idx}`;
              return (
                <li key={key} className={cn("group text-sm rounded px-1", line.shortage && "bg-rose-500/10 text-rose-700")}>
                  <div className="flex items-start justify-between gap-3">
                    <span className="min-w-0">
                      {qty(line.qty)} {line.unit} · {line.name}
                      {line.note && <span className="text-xs text-muted-foreground"> ({line.note})</span>}
                      {line.components && (
                        <span className="block text-xs text-muted-foreground">
                          No PDF: {line.components.map((c) => `${qty(c.qty)} ${c.name}`).join(", ")}
                        </span>
                      )}
                      {line.shortage && (
                        <span className="flex items-center gap-1 text-xs font-semibold">
                          <AlertTriangle className="w-3 h-3" /> Estoque insuficiente: disponível {line.available}
                        </span>
                      )}
                    </span>
                    <span className="shrink-0 flex items-center gap-1">
                      <span className="tabular-nums">{line.unit_price === null ? "sem preço" : formatBRL(line.subtotal)}</span>
                      {editing && editingLine !== key && (
                        <button type="button" onClick={() => setEditingLine(key)} title="Editar o preço deste item"
                          aria-label={`Editar o preço de ${line.name}`}
                          className="p-0.5 rounded text-muted-foreground hover:text-foreground opacity-60 group-hover:opacity-100">
                          <Pencil className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </span>
                  </div>
                  {editing && editingLine === key && (
                    <div className="flex flex-wrap items-center justify-end gap-2 py-1">
                      <span className="text-xs text-muted-foreground">Preço por {line.unit}</span>
                      <MoneyInput initial={line.unit_price} label={`Preço de ${line.name}`}
                        onCancel={() => setEditingLine(null)}
                        onSave={(value) => { editing.onPrice(line.code, value); setEditingLine(null); }} />
                    </div>
                  )}
                  {line.price_overridden && (
                    <div className="flex items-center justify-end gap-2 text-xs text-primary">
                      <span>
                        {formatBRL(line.unit_price ?? 0)} / {line.unit} editado
                        {line.catalog_unit_price !== null && line.catalog_unit_price !== undefined
                          ? ` (tabela ${formatBRL(line.catalog_unit_price)})` : " (sem preço na tabela)"}
                      </span>
                      {editing && (
                        <button type="button" className="flex items-center gap-0.5 text-muted-foreground hover:text-foreground"
                          onClick={() => editing.onPrice(line.code, null)} title="Voltar ao preço da tabela">
                          <RotateCcw className="w-3 h-3" /> tabela
                        </button>
                      )}
                    </div>
                  )}
                </li>
              );
            })}
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
        {result.manual_adjustment !== 0 && (
          <div className="flex justify-between">
            <span>{result.final_total_edited ? "Ajuste do valor final" : "Ajuste manual"}</span>
            <span className="tabular-nums">{formatBRL(result.manual_adjustment)}</span>
          </div>
        )}
        {result.periods > 1 && <div className="flex justify-between text-amber-700"><span>Períodos de locação</span><span>{result.periods} semanas</span></div>}
        <div className="flex items-center justify-between gap-2 text-lg font-bold pt-1">
          <span>Total</span>
          {editing && editingTotal ? (
            <MoneyInput initial={result.total} label="Valor final da proposta" onCancel={() => setEditingTotal(false)}
              onSave={(value) => { editing.onFinalTotal(value); setEditingTotal(false); }} />
          ) : (
            <span className="flex items-center gap-1">
              <span className="tabular-nums">{formatBRL(result.total)}</span>
              {editing && (
                <button type="button" onClick={() => setEditingTotal(true)} title="Editar o valor final que vai na proposta"
                  aria-label="Editar o valor final" className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-muted">
                  <Pencil className="w-4 h-4" />
                </button>
              )}
            </span>
          )}
        </div>
        {result.final_total_edited && (
          <div className="flex items-center justify-end gap-2 text-xs text-primary">
            <span>Valor final editado (calculado {formatBRL(result.calculated_total)})</span>
            {editing && (
              <button type="button" className="flex items-center gap-0.5 text-muted-foreground hover:text-foreground"
                onClick={() => editing.onFinalTotal(null)} title="Voltar ao valor calculado">
                <RotateCcw className="w-3 h-3" /> calculado
              </button>
            )}
          </div>
        )}
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
