import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import { formatBRL } from "@/lib/format";
import type { SingleProductForm } from "@/lib/quoteForms";
import type { Catalog } from "@/hooks/useSales";
import { NumberField, Section, SwitchField } from "./CalcFields";

const LINES = ["Som", "Iluminação", "Vídeo", "Palco e praticáveis", "Q30", "Q15", "Acessórios"];

interface Props {
  form: SingleProductForm;
  onChange: (patch: Partial<SingleProductForm>) => void;
  catalog?: Catalog;
  isAdmin: boolean;
}

export function SingleProductFields({ form, onChange, catalog, isAdmin }: Props) {
  const [line, setLine] = useState("Palco e praticáveis");
  const costOf = (code: string) => catalog?.operational_costs.find((c) => c.code === code)?.price ?? 0;
  const items = (catalog?.items || []).filter((i) => i.line === line);
  const set = <K extends keyof SingleProductForm>(key: K, value: SingleProductForm[K]) =>
    onChange({ [key]: value } as Partial<SingleProductForm>);

  return (
    <>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label className="text-xs">Data de uso</Label>
          <Input type="date" value={form.event_date} onChange={(e) => set("event_date", e.target.value)} />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Devolução (se mais de um dia)</Label>
          <Input type="date" value={form.end_date} onChange={(e) => set("end_date", e.target.value)} />
        </div>
      </div>
      <p className="text-xs text-muted-foreground">Preço de tabela, sem margem. Acima de 1 semana multiplica e vai para aprovação.</p>

      <Section title="Itens">
        <div className="flex gap-2 flex-wrap mb-3">
          {LINES.map((l) => (
            <Button key={l} size="sm" variant={line === l ? "default" : "outline"} onClick={() => setLine(l)}>{l}</Button>
          ))}
        </div>
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-2">
          {items.map((item) => (
            <div key={item.code} className={cn("flex items-center justify-between gap-3 rounded-lg border px-3 py-2",
              (form.items[item.code] || 0) > 0 && "border-primary/50 bg-primary/5")}>
              <div className="min-w-0">
                <p className="text-sm font-medium">{item.name}</p>
                <p className="text-xs text-muted-foreground">
                  {item.sale_price === null ? "sem preço (vai para aprovação)" : `${formatBRL(item.sale_price)} / ${item.billing_unit === "metro" ? "peça" : item.billing_unit}`}
                </p>
              </div>
              <Input type="number" min={0} className="w-20 h-9 shrink-0" value={form.items[item.code] || ""} placeholder="0"
                onChange={(e) => set("items", { ...form.items, [item.code]: Number(e.target.value) || 0 })} />
            </div>
          ))}
        </div>
      </Section>

      <Section title="Entrega e montagem">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2" role="radiogroup" aria-label="Forma de entrega">
          {([
            ["retirada", "Retira na LM", "Sem custo extra"],
            ["entrega", "Entrega", `Frete, carga e descarga (${formatBRL(costOf("frete") + costOf("carga") + costOf("descarga"))}). Só praticável: ${formatBRL(costOf("entrega_praticavel"))} ida e volta.`],
          ] as const).map(([value, title, hint]) => (
            <button key={value} type="button" role="radio" aria-checked={form.delivery === value}
              onClick={() => set("delivery", value)}
              className={cn("text-left rounded-lg border px-3 py-2 text-sm transition-colors",
                form.delivery === value ? "border-primary bg-primary/5" : "hover:bg-secondary")}>
              <span className="font-medium">{title}</span>
              <span className="block text-xs text-muted-foreground">{hint}</span>
            </button>
          ))}
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mt-3">
          <SwitchField id="pu-montagem" label="Com montagem" checked={form.assembly} onChange={(v) => set("assembly", v)} />
          {form.assembly && (
            <>
              <NumberField label="Pessoas" value={form.assembly_people} onChange={(v) => set("assembly_people", v)} />
              <NumberField label="Dias" value={form.assembly_days} onChange={(v) => set("assembly_days", v)} />
            </>
          )}
        </div>
        {form.assembly && (
          <p className="text-xs text-muted-foreground mt-1">Mão de obra avulsa: {formatBRL(costOf("mao_de_obra_avulsa"))} por pessoa/dia.</p>
        )}
      </Section>

      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 items-end">
        <NumberField label="Frete fora de Goiânia" suffix="R$" value={form.manual_freight} onChange={(v) => set("manual_freight", v)} />
        <NumberField label="Desconto (trava)" suffix="R$" value={form.discount} onChange={(v) => set("discount", v)} />
        {isAdmin && (
          <div className="space-y-1">
            <Label className="text-xs">Ajuste manual (R$)</Label>
            <Input type="number" step={10} value={form.manual_adjustment || ""} placeholder="0" className="h-9"
              onChange={(e) => set("manual_adjustment", Number(e.target.value) || 0)} />
          </div>
        )}
      </div>
    </>
  );
}
