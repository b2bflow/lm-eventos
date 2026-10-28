import { useEffect, useMemo, useState } from "react";
import { Loader2, RotateCcw, Save } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { formatBRL } from "@/lib/format";
import {
  type PriceRow, type PriceSettings as PriceSettingsData, type PriceSettingsPatch, usePriceSettings,
  useUpdatePriceSettings,
} from "@/hooks/useSales";

type Section = keyof PriceSettingsData;
type Draft = Record<Section, Record<string, string>>;

const SECTIONS: { key: Section; title: string; hint: string }[] = [
  { key: "metro_price", title: "Preço do metro das torres", hint: "Torres cobradas por metro (a de 2,5 m conta como 3 m). Preço por peça editado no Estoque ganha deste." },
  { key: "sound_tiers", title: "Faixas de som", hint: "Preço de cada conjunto de som. No PDF o cliente vê as peças do conjunto, não o nome dele." },
  { key: "operational_costs", title: "Custos operacionais", hint: "Carga, montagem, frete, equipe e técnicos." },
];

const rowKey = (section: Section, row: PriceRow & { line?: string; code?: string }) =>
  section === "metro_price" ? row.line! : row.code!;

const asText = (value: number | null) => (value == null ? "" : String(value).replace(".", ","));

function toDraft(data: PriceSettingsData, sections: typeof SECTIONS): Draft {
  const draft = {} as Draft;
  for (const { key } of sections) {
    draft[key] = Object.fromEntries(data[key].map((row) => [rowKey(key, row), asText(row.price)]));
  }
  return draft;
}

/** "1.300,50" ou "16,5" (vírgula decimal) e também "16.5". */
function parseMoney(text: string) {
  const t = text.trim();
  return Number(t.includes(",") ? t.replace(/\./g, "").replace(",", ".") : t);
}

function rowLabel(section: Section, row: PriceSettingsData[Section][number]) {
  if (section === "metro_price") return `Metro ${(row as { line: string }).line}`;
  return (row as { label: string }).label;
}

/**
 * Aba "Valores": preços gerais da calculadora (só admin). Campo vazio volta ao padrão do catálogo.
 * `only` mostra só algumas seções (ex.: popup "Alterar valores" da Calculadora, só custos operacionais).
 */
export function PriceSettings({ only, onSaved }: { only?: Section[]; onSaved?: () => void } = {}) {
  const { data, isLoading, isError } = usePriceSettings();
  const update = useUpdatePriceSettings();
  const [draft, setDraft] = useState<Draft | null>(null);
  const onlyKey = only?.join(",");
  const sections = useMemo(
    () => (onlyKey ? SECTIONS.filter((s) => onlyKey.split(",").includes(s.key)) : SECTIONS),
    [onlyKey],
  );
  const single = sections.length === 1;

  useEffect(() => {
    if (data) setDraft(toDraft(data, sections));
  }, [data, sections]);

  const patch = useMemo(() => {
    if (!data || !draft) return {} as PriceSettingsPatch;
    const original = toDraft(data, sections);
    const out: PriceSettingsPatch = {};
    for (const { key } of sections) {
      for (const [code, text] of Object.entries(draft[key])) {
        if (text.trim() === original[key][code]) continue;
        const value = text.trim() === "" ? null : parseMoney(text);
        (out[key] ??= {})[code] = value;
      }
    }
    return out;
  }, [data, draft, sections]);

  const changed = Object.keys(patch).length > 0;
  const invalid = Object.values(patch).some((values) =>
    Object.values(values ?? {}).some((v) => v !== null && (!Number.isFinite(v) || v < 0)),
  );

  const save = () =>
    update.mutate(patch, {
      onSuccess: () => {
        toast.success("Valores salvos. A calculadora já usa os novos preços.");
        onSaved?.();
      },
      onError: (e) =>
        toast.error((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "Não foi possível salvar os valores."),
    });

  if (isError) {
    return <p className="p-8 text-center text-sm text-destructive">Não foi possível carregar os valores.</p>;
  }
  if (isLoading || !data || !draft) {
    return <div className="flex justify-center p-8"><Loader2 className="animate-spin text-primary w-6 h-6" /></div>;
  }

  return (
    <div className="space-y-6">
      {sections.map(({ key, title, hint }) => (
        <section key={key} className={single ? "" : "p-6 rounded-2xl border border-border/50 bg-background/40 shadow-sm"}>
          {!single && (
            <div className="mb-4">
              <h3 className="text-lg font-semibold text-foreground">{title}</h3>
              <p className="text-sm text-muted-foreground">{hint}</p>
            </div>
          )}
          <div className="grid gap-4 sm:grid-cols-2 sm:items-end">
            {data[key].map((row) => {
              const code = rowKey(key, row);
              const value = draft[key][code];
              const isDefault = value.trim() === "" || value === asText(row.default);
              return (
                <div key={code} className="space-y-1.5">
                  <Label htmlFor={`price-${key}-${code}`} className="text-sm">{rowLabel(key, row)}</Label>
                  <div className="flex items-center gap-2">
                    <div className="relative flex-1">
                      <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">R$</span>
                      <Input
                        id={`price-${key}-${code}`}
                        inputMode="decimal"
                        value={value}
                        placeholder={asText(row.default)}
                        onChange={(e) => setDraft({ ...draft, [key]: { ...draft[key], [code]: e.target.value } })}
                        className="pl-9 bg-secondary/30 border-border/50"
                      />
                    </div>
                    {!isDefault && row.default != null && (
                      <Button
                        type="button" variant="ghost" size="icon" title="Voltar ao padrão"
                        onClick={() => setDraft({ ...draft, [key]: { ...draft[key], [code]: "" } })}
                      >
                        <RotateCcw className="w-4 h-4" />
                      </Button>
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground">Padrão: {row.default == null ? "sem preço" : formatBRL(row.default)}</p>
                  {"components" in row && row.components && (
                    <p className="text-xs text-muted-foreground">No PDF: {row.components}</p>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      ))}

      <div className="flex items-center justify-end gap-3">
        {invalid && <span className="text-sm text-destructive">Confira os valores: use números positivos.</span>}
        <Button variant="outline" disabled={!changed || update.isPending} onClick={() => setDraft(toDraft(data, sections))}>
          Descartar
        </Button>
        <Button disabled={!changed || invalid || update.isPending} onClick={save} className="gap-2">
          {update.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
          Salvar valores
        </Button>
      </div>
    </div>
  );
}
