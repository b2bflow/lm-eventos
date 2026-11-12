import { useMemo, useState } from "react";
import { Plus, Search, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { formatBRL } from "@/lib/format";
import type { Catalog, CatalogItem } from "@/hooks/useSales";
import { Section } from "./CalcFields";

const normalize = (text: string) => text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
const MAX_RESULTS = 8;
// Torres cobradas por metro são pedidas em peças (o preço já é por peça)
const perPiece = (item: CatalogItem) => item.billing_unit === "metro" && !!item.billed_length_m;
// Unidades que aceitam quantidade quebrada (2,5 m², 7,5 m), como no backend (FRACTIONAL_UNITS)
const isFractional = (item?: CatalogItem) => !!item && ["m²", "metro"].includes(item.billing_unit) && !perPiece(item);

const priceLabel = (item: CatalogItem) =>
  item.sale_price === null
    ? "sem preço (vai para aprovação)"
    : `${formatBRL(item.sale_price)} / ${perPiece(item) ? "peça" : item.billing_unit}`;

interface Props {
  idPrefix: string;
  catalog?: Catalog;
  /** Itens avulsos e kits do formulário ({código: quantidade}); aqui só aparecem os que não são kit. */
  extras: Record<string, number>;
  onChange: (extras: Record<string, number>) => void;
}

/** "Extras": busca qualquer item alugável do estoque e soma ao orçamento como item avulso (extra_items).
 * Os kits ficam na seção "Kits do estoque". */
export function StockExtras({ idPrefix, catalog, extras, onChange }: Props) {
  const [query, setQuery] = useState("");
  const byCode = useMemo(() => new Map((catalog?.items || []).map((i) => [i.code, i])), [catalog]);
  const searchable = useMemo(() => (catalog?.items || []).filter((i) => !i.is_kit), [catalog]);

  // Adicionados: tudo que não é kit do catálogo (inclui código que saiu do estoque, para poder tirar)
  const added = Object.entries(extras).filter(([code, qty]) => qty > 0 && !byCode.get(code)?.is_kit);

  const terms = normalize(query).split(/\s+/).filter(Boolean);
  // Todos os termos em nome, código ou linha; primeiro os que batem no começo das palavras do nome
  // ("torre 3" traz a Torre Q30 3 m antes da de 5 m, que só tem o 3 dentro de "Q30")
  const wordStarts = (item: CatalogItem) => {
    const words = normalize(item.name).split(/[\s,./()-]+/);
    return terms.filter((t) => words.some((w) => w.startsWith(t))).length;
  };
  const results = terms.length === 0 ? [] : searchable
    .filter((item) => {
      const text = normalize(`${item.name} ${item.code} ${item.line} ${item.size || ""}`);
      return terms.every((t) => text.includes(t));
    })
    .map((item, index) => ({ item, index, score: wordStarts(item) }))
    .sort((a, b) => b.score - a.score || a.index - b.index)
    .slice(0, MAX_RESULTS)
    .map(({ item }) => item);

  const setQty = (code: string, qty: number) => {
    const next = { ...extras };
    if (qty > 0) next[code] = qty;
    else delete next[code];
    onChange(next);
  };
  const add = (code: string) => {
    setQty(code, (extras[code] || 0) + 1);
    setQuery("");
  };

  return (
    <Section title="Extras">
      <p className="text-xs text-muted-foreground mb-2">
        Itens do estoque fora das seções acima, com o preço de tabela. O estoque confere a disponibilidade.
      </p>
      <div className="relative">
        <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
        <Input
          id={`${idPrefix}-extras-busca`}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && results[0]) {
              e.preventDefault();
              add(results[0].code);
            } else if (e.key === "Escape") setQuery("");
          }}
          placeholder={catalog ? "Buscar item do estoque (nome ou código)" : "Carregando estoque..."}
          disabled={!catalog}
          className="h-9 pl-9"
          aria-label="Buscar item do estoque"
          autoComplete="off"
        />
      </div>

      {terms.length > 0 && (
        <div className="mt-2 rounded-lg border divide-y max-h-80 overflow-y-auto" role="listbox" aria-label="Itens encontrados">
          {results.length === 0 && <p className="px-3 py-2 text-sm text-muted-foreground">Nenhum item encontrado.</p>}
          {results.map((item, index) => (
            <button key={item.code} type="button" role="option" aria-selected={index === 0}
              onClick={() => add(item.code)}
              className={cn("w-full flex items-center justify-between gap-3 px-3 py-2 text-left hover:bg-secondary transition-colors",
                index === 0 && "bg-secondary/50")}>
              <span className="min-w-0">
                <span className="block text-sm font-medium truncate">{item.name}</span>
                <span className="block text-xs text-muted-foreground truncate">{item.line} · {priceLabel(item)}</span>
              </span>
              <span className="shrink-0 flex items-center gap-1 text-xs text-primary">
                {(extras[item.code] || 0) > 0 && <span className="text-muted-foreground">{extras[item.code]} no orçamento</span>}
                <Plus className="w-4 h-4" />
              </span>
            </button>
          ))}
        </div>
      )}

      {added.length > 0 ? (
        <div className="mt-3 space-y-2">
          {added.map(([code, qty]) => {
            const item = byCode.get(code);
            return (
              <div key={code} className={cn("flex items-center justify-between gap-3 rounded-lg border px-3 py-2",
                item ? "border-primary/50 bg-primary/5" : "border-destructive/50 bg-destructive/5")}>
                <div className="min-w-0">
                  <p className="text-sm font-medium truncate">{item?.name || code}</p>
                  <p className={cn("text-xs truncate", item ? "text-muted-foreground" : "text-destructive")}>
                    {item
                      ? `${priceLabel(item)}${item.sale_price !== null ? ` · ${formatBRL(item.sale_price * qty)}` : ""}`
                      : "Item não está mais no estoque: remova para calcular"}
                  </p>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <Input type="number" min={0} step={isFractional(item) ? 0.5 : 1} className="w-20 h-9" value={qty}
                    aria-label={`Quantidade de ${item?.name || code}`}
                    onChange={(e) => setQty(code, Number(e.target.value) || 0)} />
                  <Button type="button" size="icon" variant="ghost" className="h-9 w-9"
                    aria-label={`Remover ${item?.name || code}`} onClick={() => setQty(code, 0)}>
                    <X className="w-4 h-4" />
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <p className="mt-2 text-xs text-muted-foreground">Nenhum extra adicionado.</p>
      )}
    </Section>
  );
}
