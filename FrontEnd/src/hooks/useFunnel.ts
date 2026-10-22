import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import api from "@/services/api";
import type { LeadStage } from "@/constants/mappings";

export interface Attachment {
  url: string;
  kind: string;
  name: string;
  received_at?: string | null;
}

export interface FunnelLead {
  id: string;
  name: string | null;
  phone: string;
  customer_state_now: LeadStage;
  product?: string | null;
  owner?: string;
  flags: string[];
  ai_qualified_at?: string | null;
  funnel_entered_at?: string | null;
  event_date?: string | null;
  event_title?: string | null;
  guest_count?: number;
  venue?: string | null;
  quoted_amount?: number;
  contract_value?: number;
  next_step?: string | null;
  next_action_at?: string | null;
  qualification: Record<string, unknown>;
  pending_fields: string[];
  attachments: Attachment[];
  human_operator?: boolean;
  needs_erica?: boolean;
  lost_reason?: string | null;
  email?: string | null;
  company?: string | null;
  role?: string | null;
  origin?: string | null;
  qualified_at?: string | null;
  first_contact_at?: string | null;
  updated_at: string;
}

export interface FunnelColumn {
  label: string;
  count: number;
  offset: number;
  has_more: boolean;
  results: FunnelLead[];
}

export type FunnelBoard = Record<LeadStage, FunnelColumn>;

export interface FunnelFilters {
  product?: string;
  owner?: string;
  flag?: string;
  search?: string;
  include_human?: boolean;
  ai_qualified?: boolean;
}

export interface TimelineEntry {
  id: string;
  action_type: string;
  description: string;
  operator_id: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface SdrTask {
  id: string;
  customer_id: string;
  customer_name: string | null;
  customer_phone: string | null;
  type: string;
  label: string;
  due_at: string;
  status: string;
}

export interface LockReason {
  code: string;
  message: string;
  detail?: string | null;
}

export interface ProposalLine {
  code: string;
  name: string;
  block: string;
  qty: number;
  unit: string;
  unit_price: number | null;
  subtotal: number;
  periods?: number;
  note?: string | null;
  available?: number | null;
  shortage?: boolean;
  owned?: boolean;
}

export interface Proposal {
  id: string;
  customer_id: string;
  customer_name?: string | null;
  version: number;
  mode: string;
  inputs: Record<string, unknown>;
  lines: ProposalLine[];
  costs: { code: string; name: string; subtotal: number }[];
  items_total: number;
  costs_total: number;
  margin_pct: number;
  with_invoice: boolean;
  invoice_value: number;
  manual_adjustment: number;
  total: number;
  status: string;
  status_label: string;
  lock_reasons: LockReason[];
  warnings: string[];
  valid_until: string | null;
  sent_at: string | null;
  created_at: string;
}

const cleanFilters = (filters: FunnelFilters) => {
  const params: Record<string, string> = {};
  if (filters.product) params.product = filters.product;
  if (filters.owner) params.owner = filters.owner;
  if (filters.flag) params.flag = filters.flag;
  if (filters.search) params.search = filters.search;
  if (filters.include_human) params.include_human = "true";
  if (filters.ai_qualified) params.ai_qualified = "true";
  return params;
};

export function useFunnelBoard(filters: FunnelFilters) {
  return useQuery({
    queryKey: ["funnel", filters],
    queryFn: async () => (await api.get<FunnelBoard>("/crm/funnel/", { params: cleanFilters(filters) })).data,
    refetchInterval: 60000,
  });
}

export async function fetchMoreForStage(stage: LeadStage, offset: number, filters: FunnelFilters) {
  const { data } = await api.get<FunnelBoard>("/crm/funnel/", { params: { ...cleanFilters(filters), stage, offset } });
  return data[stage];
}

export function useLead(id: string | null) {
  return useQuery({
    queryKey: ["lead", id],
    queryFn: async () => (await api.get<FunnelLead>(`/crm/customers/${id}/`)).data,
    enabled: !!id,
  });
}

export function useTimeline(id: string | null) {
  return useQuery({
    queryKey: ["lead-timeline", id],
    queryFn: async () => (await api.get<TimelineEntry[]>(`/crm/customers/${id}/timeline/`)).data,
    enabled: !!id,
  });
}

export function useLeadTasks(id: string | null) {
  return useQuery({
    queryKey: ["lead-tasks", id],
    queryFn: async () => (await api.get<SdrTask[]>(`/crm/customers/${id}/tasks/`)).data,
    enabled: !!id,
  });
}

export function useSdrQueue() {
  return useQuery({
    queryKey: ["sdr-tasks"],
    queryFn: async () => (await api.get<SdrTask[]>("/crm/tasks/")).data,
    refetchInterval: 60000,
  });
}

export function useProposals(customerId: string | null) {
  return useQuery({
    queryKey: ["proposals", customerId],
    queryFn: async () => (await api.get<Proposal[]>("/sales/proposals/", { params: { customer: customerId } })).data,
    enabled: !!customerId,
  });
}

function errorDetail(error: unknown, fallback: string): string {
  const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
  return detail || fallback;
}

/** Ações do card: todas invalidam funil, lead, linha do tempo e tarefas. */
export function useLeadActions(id: string | null) {
  const queryClient = useQueryClient();
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["funnel"] });
    queryClient.invalidateQueries({ queryKey: ["lead", id] });
    queryClient.invalidateQueries({ queryKey: ["lead-timeline", id] });
    queryClient.invalidateQueries({ queryKey: ["lead-tasks", id] });
    queryClient.invalidateQueries({ queryKey: ["sdr-tasks"] });
    queryClient.invalidateQueries({ queryKey: ["proposals", id] });
    queryClient.invalidateQueries({ queryKey: ["leads"] });
  };
  const mutation = useMutation({
    mutationFn: (v: { path: string; body?: unknown; success: string; fallback: string }) => api.post(v.path, v.body),
    onSuccess: (_data, v) => {
      toast.success(v.success);
      refresh();
    },
    onError: (error, v) => toast.error(errorDetail(error, v.fallback)),
  });
  const post = (path: string, body: unknown, success: string, fallback: string) =>
    mutation.mutateAsync({ path, body, success, fallback });

  return {
    isPending: mutation.isPending,
    changeStage: (body: { stage: LeadStage; lost_reason?: string }, leadId?: string) =>
      post(`/crm/customers/${leadId ?? id}/stage/`, body, "Etapa atualizada.", "Não foi possível mudar a etapa."),
    setFlags: (body: { add?: string[]; remove?: string[] }) =>
      post(`/crm/customers/${id}/flags/`, body, "Sinalizações atualizadas.", "Não foi possível alterar as sinalizações."),
    setNextAction: (body: { next_step: string; next_action_at: string | null }) =>
      post(`/crm/customers/${id}/next-action/`, body, "Próxima ação salva.", "Não foi possível salvar a próxima ação."),
    addNote: (text: string) =>
      post(`/crm/customers/${id}/notes/`, { text }, "Nota adicionada.", "Não foi possível salvar a nota."),
    logCall: (body: { outcome: string; notes?: string }) =>
      post(`/crm/customers/${id}/calls/`, body, "Ligação registrada.", "Não foi possível registrar a ligação."),
    completeTask: (taskId: string) =>
      post(`/crm/tasks/${taskId}/done/`, {}, "Tarefa concluída.", "Não foi possível concluir a tarefa."),
    proposalAction: (proposalId: string, action: "send" | "accept" | "reject" | "approve", extra?: { approve?: boolean; note?: string }) =>
      post(`/sales/proposals/${proposalId}/${action}/`, extra ?? {}, "Proposta atualizada.", "Não foi possível atualizar a proposta."),
    sendProposalWhatsApp: (proposalId: string) =>
      post(`/sales/proposals/${proposalId}/send-whatsapp/`, {}, "Proposta enviada no WhatsApp do cliente.",
        "Não foi possível enviar a proposta pelo WhatsApp."),
  };
}

export function useCurrentUser() {
  return useQuery({
    queryKey: ["user-profile"],
    queryFn: async () => (await api.get<{ id: number; username: string; first_name: string; is_staff: boolean; role?: string }>("/users/me/")).data,
    staleTime: 5 * 60 * 1000,
  });
}

export function isAdminUser(user?: { is_staff?: boolean; role?: string }) {
  return !!user && (user.is_staff || user.role === "admin");
}
