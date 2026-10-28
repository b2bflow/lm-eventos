/** Estados dos formulários da calculadora e conversão para as entradas do backend
 * (sales/services/quote_calculator.py: CorporateInput, SocialInput, SingleProductInput). */

export type Band = "nenhuma" | "voz_violao" | "completa";
export type EventVariant = "corporativo" | "social";

export interface EventForm {
  guests: number;
  event_date: string;
  band: Band;
  dance_floor: boolean;
  stage_m2: number;
  stage_covered: boolean;
  led_m2: number;
  led_technician: boolean;
  led_structure: number;
  backdrop: number;
  lights: Record<string, number>;
  extra_mics: number;
  tp: number;
  praticaveis: number;
  slide_passer: number;
  digital_mixer: number;
  pass_cable_m: number;
  // Serviços opcionais: desligados por padrão, seção desligada não soma nada
  sound_enabled: boolean;
  stage_video_enabled: boolean;
  lighting_enabled: boolean;
  operational: string[];
  manual_freight: number;
  project_cost: number;
  margin: number;
  with_invoice: boolean;
  discount: number;
  manual_adjustment: number;
  // Social
  structure: string;
  ceremony_sound: boolean;
  /** Peças do som de cerimônia escolhidas na calculadora; null = composição padrão. */
  ceremony_items: Record<string, number> | null;
  dj: boolean;
  has_project: boolean;
  competitor_quote: boolean;
}

export interface SingleProductForm {
  event_date: string;
  end_date: string;
  items: Record<string, number>;
  delivery: "retirada" | "entrega";
  assembly: boolean;
  assembly_people: number;
  assembly_days: number;
  manual_freight: number;
  discount: number;
  manual_adjustment: number;
}

export const CORPORATE_LIGHTS = ["luz_moving_beam", "luz_par_led", "luz_par_38", "luz_ribalta", "luz_atomic", "luz_p5"];
export const SOCIAL_LIGHTS = [
  "luz_pontual", "luz_par_38", "luz_par_led", "luz_moving_beam", "luz_fumaca", "luz_piso_microlampadas",
];

export const emptyEvent = (variant: EventVariant): EventForm => ({
  guests: 0, event_date: "", band: "nenhuma", dance_floor: variant === "social", stage_m2: 0, stage_covered: true,
  led_m2: 0, led_technician: false, led_structure: 0, backdrop: 0, lights: {}, extra_mics: 0, tp: 0, praticaveis: 0,
  slide_passer: 0, digital_mixer: 0, pass_cable_m: 0,
  sound_enabled: false, stage_video_enabled: false, lighting_enabled: false, operational: ["carga", "descarga", "frete", "alimentacao"],
  manual_freight: 0, project_cost: 0, margin: 0, with_invoice: true, discount: 0, manual_adjustment: 0,
  structure: "nenhuma", ceremony_sound: false, ceremony_items: null, dj: variant === "social", has_project: false, competitor_quote: false,
});

export const emptySingleProduct = (): SingleProductForm => ({
  event_date: "", end_date: "", items: {}, delivery: "retirada", assembly: false, assembly_people: 0,
  assembly_days: 1, manual_freight: 0, discount: 0, manual_adjustment: 0,
});

const COMMON_EVENT_KEYS: (keyof EventForm)[] = [
  "guests", "event_date", "band", "dance_floor", "stage_m2", "stage_covered", "led_m2", "led_structure", "backdrop",
  "lights", "extra_mics", "praticaveis", "operational", "manual_freight", "project_cost", "margin", "with_invoice",
  "discount", "manual_adjustment", "sound_enabled", "stage_video_enabled", "lighting_enabled",
];
const VARIANT_KEYS: Record<EventVariant, (keyof EventForm)[]> = {
  corporativo: ["led_technician", "tp", "slide_passer", "digital_mixer", "pass_cable_m"],
  social: ["structure", "ceremony_sound", "ceremony_items", "dj", "has_project", "competitor_quote"],
};

const positive = (record: Record<string, number>) => Object.fromEntries(Object.entries(record).filter(([, q]) => q > 0));

/** Só as chaves do modo, para o snapshot da proposta não carregar campos do outro modo. */
export function eventInputs(variant: EventVariant, form: EventForm, isAdmin: boolean) {
  const keys = [...COMMON_EVENT_KEYS, ...VARIANT_KEYS[variant]];
  const inputs: Record<string, unknown> = Object.fromEntries(keys.map((k) => [k, form[k]]));
  inputs.lights = positive(form.lights);
  // Sem margem: a tabela já tem a margem da Erica (vale também ao reabrir proposta antiga com margem)
  inputs.margin = 0;
  if (!isAdmin) inputs.manual_adjustment = 0;
  return inputs;
}

/** Proposta salva antes das chaves de serviço: as três seções contavam, então abrem ligadas. */
export function withServiceDefaults(inputs: Partial<EventForm>): Partial<EventForm> {
  return {
    ...inputs,
    sound_enabled: inputs.sound_enabled ?? true,
    stage_video_enabled: inputs.stage_video_enabled ?? true,
    lighting_enabled: inputs.lighting_enabled ?? true,
  };
}

export function singleProductInputs(form: SingleProductForm, isAdmin: boolean) {
  return {
    ...form,
    end_date: form.end_date || undefined,
    items: Object.entries(positive(form.items)).map(([code, qty]) => ({ code, qty })),
    manual_adjustment: isAdmin ? form.manual_adjustment : 0,
  };
}

/** "24/10/2026" ou "2026-10-24..." -> "2026-10-24" */
export function toIsoDay(value: unknown): string {
  if (typeof value !== "string" || !value) return "";
  const br = value.match(/^(\d{2})\/(\d{2})\/(\d{4})/);
  if (br) return `${br[3]}-${br[2]}-${br[1]}`;
  return /^\d{4}-\d{2}-\d{2}/.test(value) ? value.slice(0, 10) : "";
}

/** Resposta de qualificação em texto livre ("sim", "Tenho sim", true...) como booleano. */
export function answeredYes(value: unknown): boolean {
  if (typeof value === "boolean") return value;
  if (typeof value !== "string") return false;
  const text = value.normalize("NFD").replace(/[̀-ͯ]/g, "").trim().toLowerCase();
  return /^(sim|s|yes|true|tenho|tem|quero)\b/.test(text);
}
