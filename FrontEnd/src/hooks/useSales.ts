import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import api from "@/services/api";
import type { LockReason, Proposal, ProposalLine } from "@/hooks/useFunnel";

export interface CatalogItem {
  code: string;
  line: string;
  name: string;
  size: string | null;
  billing_unit: string;
  sale_price: number | null;
  owned: boolean;
  block: string | null;
  note: string | null;
}

export interface Catalog {
  lines: string[];
  items: CatalogItem[];
  operational_costs: { code: string; label: string; price: number }[];
  margin_levels: number[];
  invoice_rate: number;
  approval_ceiling: number;
  proposal_validity_days: number;
  kits: { code: string; label: string; pieces: { code: string; qty: number }[] }[];
  sound_tiers?: [number | null, string][];
  social_basic_package: {
    structure: string;
    led_m2: number;
    dance_floor: boolean;
    lights: Record<string, number>;
    dj: boolean;
    sound_enabled: boolean;
    stage_video_enabled: boolean;
    lighting_enabled: boolean;
    operational: string[];
  };
  social_max_guests: number;
  social_max_total: number;
}

export interface QuoteResult {
  mode: string;
  lines: ProposalLine[];
  operational: { code: string; name: string; subtotal: number }[];
  items_total: number;
  costs_total: number;
  subtotal: number;
  margin_pct: number;
  margin_value: number;
  with_invoice: boolean;
  invoice_value: number;
  discount: number;
  manual_adjustment: number;
  total: number;
  periods: number;
  locked: boolean;
  lock_reasons: LockReason[];
  warnings: string[];
  pending_items: string[];
  requires_technical_visit: boolean;
  requires_meeting: boolean;
  /** Total calculado antes do valor final editado. */
  calculated_total: number;
  final_total_edited: boolean;
  period_start: string;
  period_end: string;
}

export interface InventoryRow {
  id: string;
  code: string;
  line: string;
  name: string;
  size: string | null;
  billing_unit: string;
  qty_total: number | null;
  owned: boolean;
  rentable: boolean;
  approximate_count: boolean;
  counted_at: string | null;
  note: string | null;
  description: string | null;
  active: boolean;
  observations_count: number;
  sale_price: number | null;
  reserved: number | null;
  available: number | null;
}

export interface InventoryObservation {
  id: string;
  kind: "nota" | "ajuste";
  text: string;
  author_id: string | null;
  author_name: string | null;
  created_at: string;
}

export interface InventoryReservation {
  id: string;
  item_id: string;
  item_name: string;
  proposal_id: string | null;
  manual: boolean;
  customer_name: string | null;
  qty: number;
  start: string;
  end: string; // exclusivo (dia seguinte ao último)
  status: string;
  note: string | null;
  created_by: string | null;
  created_by_name: string | null;
}

export interface InventoryMovement {
  id: string;
  customer_name: string | null;
  qty: number;
  type: "saida" | "retorno";
  date: string;
  note: string | null;
}

export interface InventoryItemDetail extends Omit<InventoryRow, "reserved" | "available"> {
  observations: InventoryObservation[];
  reservations: InventoryReservation[];
  movements: InventoryMovement[];
  reservations_enabled: boolean;
}

/** Abre o PDF da proposta numa nova aba (a rota exige login, então baixa com o token). */
export async function openProposalPdf(id: string) {
  const win = window.open("", "_blank");
  const { data } = await api.get<Blob>(`/sales/proposals/${id}/pdf/`, { responseType: "blob" });
  const url = URL.createObjectURL(data);
  if (win) win.location.href = url;
  else window.location.href = url;
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

export function useCatalog() {
  return useQuery({
    queryKey: ["sales-catalog"],
    queryFn: async () => (await api.get<Catalog>("/sales/catalog/")).data,
    staleTime: 5 * 60 * 1000,
  });
}

export interface PriceRow {
  price: number | null;
  default: number | null;
}

export interface PriceSettings {
  metro_price: (PriceRow & { line: string })[];
  operational_costs: (PriceRow & { code: string; label: string })[];
  sound_tiers: (PriceRow & { code: string; label: string; limit: number | null })[];
}

export type PriceSettingsPatch = Partial<Record<keyof PriceSettings, Record<string, number | null>>>;

/** Valores gerais da calculadora (aba "Valores" em Configurações). */
export function usePriceSettings() {
  return useQuery({
    queryKey: ["sales-prices"],
    queryFn: async () => (await api.get<PriceSettings>("/sales/prices/")).data,
  });
}

/** Grava os valores (só admin); null volta ao padrão do catálogo. */
export function useUpdatePriceSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (patch: PriceSettingsPatch) => (await api.patch<PriceSettings>("/sales/prices/", patch)).data,
    onSuccess: (data) => {
      queryClient.setQueryData(["sales-prices"], data);
      queryClient.invalidateQueries({ queryKey: ["sales-catalog"] });
    },
  });
}

export function useProposal(id: string | null) {
  return useQuery({
    queryKey: ["proposal", id],
    queryFn: async () => (await api.get<Proposal>(`/sales/proposals/${id}/`)).data,
    enabled: !!id,
  });
}

export function useInventory(line: string | undefined, start: string, end: string, includeInactive = false) {
  return useQuery({
    queryKey: ["inventory", line, start, end, includeInactive],
    queryFn: async () => {
      const params: Record<string, string> = { start, end };
      if (line) params.line = line;
      if (includeInactive) params.include_inactive = "1";
      return (await api.get<InventoryRow[]>("/inventory/items/", { params })).data;
    },
    enabled: !!start,
  });
}

/** Ficha do item: observações, reservas ativas e últimas movimentações. */
export function useInventoryItem(id: string | null) {
  return useQuery({
    queryKey: ["inventory-item", id],
    queryFn: async () => (await api.get<InventoryItemDetail>(`/inventory/items/${id}/`)).data,
    enabled: !!id,
  });
}
