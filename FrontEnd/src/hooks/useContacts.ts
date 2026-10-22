import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import api from "@/services/api";
import type { Attachment, TimelineEntry } from "@/hooks/useFunnel";

export interface ContactSummary {
  id: string;
  name: string | null;
  phone: string;
  email: string | null;
  company: string | null;
  role: string | null;
  contact_type: string;
  origin: string | null;
  owner: string;
  human_operator: boolean;
  notes: string | null;
  last_interaction_at: string | null;
  created_at: string | null;
  updated_at: string | null;
  current_lead?: { stage: string; product: string | null } | null;
  leads_count?: number;
}

export interface ContactLeadProposal {
  id: string;
  version: number;
  mode: string;
  total: number;
  status: string;
  status_label: string;
  sent_at: string | null;
  created_at: string | null;
}

export interface ContactLead {
  id: string;
  number: number;
  current: boolean;
  stage: string;
  product: string | null;
  lost_reason: string | null;
  qualification: Record<string, unknown>;
  pending_fields: string[];
  attachments: Attachment[];
  quoted_amount: number;
  contract_value: number;
  event_date: string | null;
  guest_count: number;
  venue: string | null;
  started_at: string | null;
  closed_at: string | null;
  proposals: ContactLeadProposal[];
}

export interface ContactDetail extends ContactSummary {
  lead_number: number;
  /** O lead atual está no quadro do funil (leads de antes do início pela plataforma não estão). */
  in_funnel: boolean;
  current_lead_open: boolean;
  leads: ContactLead[];
  attachments: (Attachment & { lead_number: number })[];
  conversation_id: string | null;
}

export interface ContactFilters {
  search?: string;
  contact_type?: string;
  owner?: string;
  partner?: boolean;
}

export interface ImportResult {
  total: number;
  created: number;
  updated: number;
  unchanged: number;
  repeated: number;
  dry_run: boolean;
  invalid: { line: number; value: string; reason: string }[];
  rows: { line: number; phone: string; name: string | null; existing_name: string | null; action: string }[];
}

interface ContactPage {
  count: number;
  page: number;
  has_more: boolean;
  results: ContactSummary[];
}

const PAGE_SIZE = 30;

export function useContacts(filters: ContactFilters) {
  return useInfiniteQuery({
    queryKey: ["contacts", filters],
    initialPageParam: 1,
    queryFn: async ({ pageParam }) => {
      const params: Record<string, string | number> = { page: pageParam, page_size: PAGE_SIZE };
      if (filters.search) params.search = filters.search;
      if (filters.contact_type) params.contact_type = filters.contact_type;
      if (filters.owner) params.owner = filters.owner;
      if (filters.partner !== undefined) params.partner = String(filters.partner);
      return (await api.get<ContactPage>("/crm/contacts/", { params })).data;
    },
    getNextPageParam: (last) => (last.has_more ? last.page + 1 : undefined),
  });
}

export function useContact(id: string | null) {
  return useQuery({
    queryKey: ["contact", id],
    queryFn: async () => (await api.get<ContactDetail>(`/crm/contacts/${id}/`)).data,
    enabled: !!id,
  });
}

export function useContactLeadTimeline(contactId: string | null, leadId: string | null) {
  return useQuery({
    queryKey: ["contact-timeline", contactId, leadId],
    queryFn: async () =>
      (await api.get<TimelineEntry[]>(`/crm/contacts/${contactId}/timeline/`, { params: { lead: leadId } })).data,
    enabled: !!contactId && !!leadId,
  });
}

export function errorDetail(error: unknown, fallback: string): string {
  const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
  return detail || fallback;
}

export function useContactActions(id: string | null) {
  const queryClient = useQueryClient();
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["contacts"] });
    queryClient.invalidateQueries({ queryKey: ["contact", id] });
    queryClient.invalidateQueries({ queryKey: ["funnel"] });
    queryClient.invalidateQueries({ queryKey: ["lead", id] });
  };

  const update = useMutation({
    mutationFn: async (body: Partial<ContactSummary>) => (await api.patch<ContactDetail>(`/crm/contacts/${id}/`, body)).data,
    onSuccess: () => {
      toast.success("Contato salvo.");
      refresh();
    },
    onError: (error) => toast.error(errorDetail(error, "Não foi possível salvar o contato.")),
  });

  const newLead = useMutation({
    mutationFn: async (product: string) => (await api.post<ContactDetail>(`/crm/contacts/${id}/new-lead/`, { product })).data,
    onSuccess: () => {
      toast.success("Novo lead aberto no funil.");
      refresh();
    },
    onError: (error) => toast.error(errorDetail(error, "Não foi possível abrir o lead.")),
  });

  return { update, newLead };
}

export function useCreateContact() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: Partial<ContactSummary>) => (await api.post<ContactDetail>("/crm/contacts/", body)).data,
    onSuccess: () => {
      toast.success("Contato cadastrado.");
      queryClient.invalidateQueries({ queryKey: ["contacts"] });
      queryClient.invalidateQueries({ queryKey: ["funnel"] });
    },
  });
}

export function useImportPartners() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ file, dryRun }: { file: File; dryRun: boolean }) => {
      const form = new FormData();
      form.append("file", file);
      form.append("dry_run", String(dryRun));
      return (await api.post<ImportResult>("/crm/contacts/import-partners/", form, {
        headers: { "Content-Type": "multipart/form-data" },
      })).data;
    },
    onSuccess: (result) => {
      if (!result.dry_run) {
        queryClient.invalidateQueries({ queryKey: ["contacts"] });
        queryClient.invalidateQueries({ queryKey: ["funnel"] });
      }
    },
    onError: (error) => toast.error(errorDetail(error, "Não foi possível ler o arquivo.")),
  });
}
