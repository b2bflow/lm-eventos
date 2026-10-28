import { PackageCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { formatBRL } from "@/lib/format";
import { CORPORATE_LIGHTS, SOCIAL_LIGHTS, type Band, type EventForm, type EventVariant } from "@/lib/quoteForms";
import type { Catalog } from "@/hooks/useSales";
import { NumberField, Section, SwitchField, ToggleSection } from "./CalcFields";

// Custos que só fazem sentido no produto único; o DJ do social tem chave própria.
const HIDDEN_COSTS: Record<EventVariant, string[]> = {
  corporativo: ["mao_de_obra_avulsa", "entrega_praticavel"],
  social: ["mao_de_obra_avulsa", "entrega_praticavel", "dj"],
};

interface Props {
  variant: EventVariant;
  form: EventForm;
  onChange: (patch: Partial<EventForm>) => void;
  catalog?: Catalog;
  isAdmin: boolean;
}

export function EventFormFields({ variant, form, onChange, catalog, isAdmin }: Props) {
  const social = variant === "social";
  const set = <K extends keyof EventForm>(key: K, value: EventForm[K]) => onChange({ [key]: value } as Partial<EventForm>);
  const itemName = (code: string) => catalog?.items.find((i) => i.code === code)?.name || code;
  const lights = social ? SOCIAL_LIGHTS : CORPORATE_LIGHTS;
  const id = (name: string) => `${variant}-${name}`;
  const soundSystem = form.guests > 0 && catalog?.sound_tiers
    ? catalog.sound_tiers.find(([limit]) => limit === null || form.guests <= limit)?.[1]
    : undefined;
  // Conjuntos de som: o PDF mostra as peças, não o nome do conjunto
  const pieceName = (code: string) => (code === "som_mic_sem_fio" ? "Microfone sem fio" : itemName(code));
  const pieces = (code?: string) =>
    (code && catalog?.sound_sets?.[code]?.map((p) => `${p.qty} ${pieceName(p.code)}`).join(" + ")) || "";
  const ceremonyDefault = catalog?.sound_sets?.som_cerimonia ?? [];
  const kits = (catalog?.items || []).filter((i) => i.is_kit);
  const ceremonyQty = (code: string) =>
    form.ceremony_items?.[code] ?? ceremonyDefault.find((p) => p.code === code)?.qty ?? 0;
  const setCeremonyQty = (code: string, value: number) => set("ceremony_items",
    { ...Object.fromEntries(ceremonyDefault.map((p) => [p.code, ceremonyQty(p.code)])), [code]: value });

  const applyBasicPackage = () => {
    const pkg = catalog?.social_basic_package;
    if (!pkg) return;
    onChange({ ...pkg, lights: { ...pkg.lights }, operational: [...pkg.operational] });
  };

  return (
    <>
      {social && (
        <div className="rounded-lg border border-primary/30 bg-primary/5 p-3 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <p className="text-sm">
            Pacote básico: gol 3x4, LED 3x2, som até 150, luz e DJ.
            <span className="block text-xs text-muted-foreground">
              Acima de {catalog?.social_max_guests ?? 200} convidados, de {formatBRL(catalog?.social_max_total ?? 6000)},
              com projeto ou orçamento concorrente: reunião com a Erica.
            </span>
          </p>
          <Button size="sm" variant="outline" onClick={applyBasicPackage} disabled={!catalog}>
            <PackageCheck className="w-4 h-4 mr-1.5" /> Pacote básico
          </Button>
        </div>
      )}

      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <NumberField label={social ? "Convidados" : "Pessoas"} value={form.guests} onChange={(v) => set("guests", v)} />
        <div className="space-y-1 col-span-1 sm:col-span-2">
          <Label className="text-xs">Data do evento</Label>
          <Input type="date" value={form.event_date} onChange={(e) => set("event_date", e.target.value)} />
        </div>
        {social && <SwitchField id={id("dj")} label="DJ" checked={form.dj} onChange={(v) => set("dj", v)} />}
      </div>

      {social && (
        <Section title="Estrutura">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="space-y-1">
              <Label className="text-xs">Kit Q30</Label>
              <Select value={form.structure} onValueChange={(v) => set("structure", v)}>
                <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="nenhuma">Nenhuma</SelectItem>
                  {(catalog?.kits || []).map((kit) => <SelectItem key={kit.code} value={kit.code}>{kit.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <SwitchField id={id("projeto")} label="Cliente tem projeto" checked={form.has_project} onChange={(v) => set("has_project", v)} />
            <SwitchField id={id("concorrente")} label="Orçamento concorrente" checked={form.competitor_quote}
              onChange={(v) => set("competitor_quote", v)} />
          </div>
        </Section>
      )}

      <ToggleSection id={id("som")} title="Som" hint="Sistema pela faixa de público, com caixas e 1 microfone sem fio"
        enabled={form.sound_enabled} onToggle={(v) => set("sound_enabled", v)}>
        <label className="flex items-center gap-2 text-sm mb-3">
          <Checkbox checked disabled />
          {soundSystem ? itemName(soundSystem) : "Sistema de som"}{" "}
          <span className="text-muted-foreground">({pieces(soundSystem) || "1 microfone sem fio incluso"})</span>
        </label>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          <div className="space-y-1">
            <Label className="text-xs">Banda</Label>
            <Select value={form.band} onValueChange={(v) => set("band", v as Band)}>
              <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="nenhuma">Nenhuma</SelectItem>
                <SelectItem value="voz_violao">Voz e violão (+1 microfone)</SelectItem>
                <SelectItem value="completa">Completa (backline)</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <SwitchField id={id("pista")} label="Pista" checked={form.dance_floor} onChange={(v) => set("dance_floor", v)} />
          <NumberField label="Microfones extras" suffix="além dos inclusos" value={form.extra_mics} onChange={(v) => set("extra_mics", v)} />
          {!social && <NumberField label="Mesa digital" value={form.digital_mixer} onChange={(v) => set("digital_mixer", v)} />}
          {social && (
            <SwitchField id={id("cerimonia")} label="Som de cerimônia" checked={form.ceremony_sound}
              onChange={(v) => set("ceremony_sound", v)} />
          )}
        </div>
        {social && form.ceremony_sound && ceremonyDefault.length > 0 && (
          <div className="mt-3 rounded-lg border border-border/60 p-3 space-y-2">
            <p className="text-xs text-muted-foreground">
              Peças do som de cerimônia (o PDF mostra as peças, não o nome do conjunto)
            </p>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {ceremonyDefault.map((p) => (
                <NumberField key={p.code} label={pieceName(p.code)} value={ceremonyQty(p.code)}
                  onChange={(v) => setCeremonyQty(p.code, v)} />
              ))}
            </div>
          </div>
        )}
      </ToggleSection>

      <ToggleSection id={id("palco")} title="Palco e vídeo" enabled={form.stage_video_enabled}
        onToggle={(v) => set("stage_video_enabled", v)}>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          <NumberField label="Palco" suffix="m²" value={form.stage_m2} step={0.5} onChange={(v) => set("stage_m2", v)} />
          <SwitchField id={id("forrado")} label="Forrado" checked={form.stage_covered} onChange={(v) => set("stage_covered", v)} />
          <NumberField label="Praticáveis 2x1" value={form.praticaveis} onChange={(v) => set("praticaveis", v)} />
          <NumberField label="Backdrop" value={form.backdrop} onChange={(v) => set("backdrop", v)} />
          {!social && <NumberField label="Passa-cabo" suffix="m" value={form.pass_cable_m} onChange={(v) => set("pass_cable_m", v)} />}
          <NumberField label={social ? "Painel de LED (técnico incluso)" : "Painel de LED"} suffix="m²" value={form.led_m2}
            step={0.5} onChange={(v) => set("led_m2", v)} />
          {!social && (
            <SwitchField id={id("tecled")} label="Técnico de LED" checked={form.led_technician} onChange={(v) => set("led_technician", v)} />
          )}
          <NumberField label="Estrutura de LED" value={form.led_structure} onChange={(v) => set("led_structure", v)} />
          {!social && (
            <>
              <NumberField label="TP (TV de retorno)" value={form.tp} onChange={(v) => set("tp", v)} />
              <NumberField label="Passador de slides" value={form.slide_passer} onChange={(v) => set("slide_passer", v)} />
            </>
          )}
        </div>
      </ToggleSection>

      <ToggleSection id={id("luz")} title="Iluminação" enabled={form.lighting_enabled} onToggle={(v) => set("lighting_enabled", v)}>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          {lights.map((code) => (
            <NumberField key={code} label={itemName(code)} value={form.lights[code] || 0}
              onChange={(v) => set("lights", { ...form.lights, [code]: v })} />
          ))}
        </div>
      </ToggleSection>

      {kits.length > 0 && (
        <Section title="Kits do estoque">
          <p className="text-xs text-muted-foreground mb-2">Preço do kit; o estoque confere as peças e o PDF lista as peças.</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {kits.map((kit) => (
              <NumberField key={kit.code} label={kit.name}
                suffix={`${kit.sale_price === null ? "sem preço" : formatBRL(kit.sale_price)} · ${pieces(kit.code)}`}
                value={form.kits?.[kit.code] || 0} onChange={(v) => set("kits", { ...form.kits, [kit.code]: v })} />
            ))}
          </div>
        </Section>
      )}

      <Section title="Custos operacionais">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {(catalog?.operational_costs || []).filter((c) => !HIDDEN_COSTS[variant].includes(c.code)).map((cost) => (
            <label key={cost.code} className="flex items-center gap-2 text-sm">
              <Checkbox
                checked={form.operational.includes(cost.code)}
                onCheckedChange={(checked) => set("operational", checked
                  ? [...form.operational, cost.code]
                  : form.operational.filter((c) => c !== cost.code))}
              />
              {cost.label} <span className="text-muted-foreground">{formatBRL(cost.price)}</span>
            </label>
          ))}
        </div>
        <div className="grid grid-cols-2 gap-3 mt-3">
          <NumberField label="Frete fora de Goiânia" suffix="R$" value={form.manual_freight} onChange={(v) => set("manual_freight", v)} />
          <NumberField label="Custo de projeto (trava)" suffix="R$" value={form.project_cost} onChange={(v) => set("project_cost", v)} />
        </div>
      </Section>

      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 items-end">
        <div className="flex items-center gap-2 pb-2">
          <Switch checked={form.with_invoice} onCheckedChange={(v) => set("with_invoice", v)} id={id("nf")} />
          <Label htmlFor={id("nf")} className="text-sm">{form.with_invoice ? "Com nota" : "Sem nota"}</Label>
        </div>
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
