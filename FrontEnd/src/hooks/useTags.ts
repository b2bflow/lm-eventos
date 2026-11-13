import { useMemo } from "react";
import { QueryClient, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import api from "@/services/api";
import type { ContactDetail } from "@/hooks/useContacts";
import type { ConversationsData } from "@/hooks/useConversations";

/** Tag (etiqueta) do cliente. `key` é o que fica no cliente; `name` e `color` podem mudar. */
export interface CustomerTag {
  id: string;
  key: string;
  name: string;
  color: string;
  /** Automática (IA/orçamento): não pode ser excluída. */
  builtin: boolean;
  /** Só com ?counts=1: quantos contatos têm a tag. */
  count?: number;
}

export const TAG_COLORS = ["slate", "red", "orange", "amber", "lime", "emerald", "teal", "sky", "blue", "violet", "pink"] as const;

export const TAG_COLOR_LABELS: Record<string, string> = {
  slate: "Cinza", red: "Vermelho", orange: "Laranja", amber: "Amarelo", lime: "Verde-limão", emerald: "Verde",
  teal: "Verde-água", sky: "Azul-claro", blue: "Azul", violet: "Roxo", pink: "Rosa",
};

export const TAG_COLOR_STYLES: Record<string, string> = {
  slate: "bg-slate-500/10 text-slate-700 border-slate-500/30 dark:text-slate-300",
  red: "bg-red-500/10 text-red-700 border-red-500/30 dark:text-red-300",
  orange: "bg-orange-500/10 text-orange-700 border-orange-500/30 dark:text-orange-300",
  amber: "bg-amber-500/10 text-amber-700 border-amber-500/30 dark:text-amber-300",
  lime: "bg-lime-500/10 text-lime-700 border-lime-500/30 dark:text-lime-300",
  emerald: "bg-emerald-500/10 text-emerald-700 border-emerald-500/30 dark:text-emerald-300",
  teal: "bg-teal-500/10 text-teal-700 border-teal-500/30 dark:text-teal-300",
  sky: "bg-sky-500/10 text-sky-700 border-sky-500/30 dark:text-sky-300",
  blue: "bg-blue-500/10 text-blue-700 border-blue-500/30 dark:text-blue-300",
  violet: "bg-violet-500/10 text-violet-700 border-violet-500/30 dark:text-violet-300",
  pink: "bg-pink-500/10 text-pink-700 border-pink-500/30 dark:text-pink-300",
};

export const TAG_COLOR_DOTS: Record<string, string> = {
  slate: "bg-slate-500", red: "bg-red-500", orange: "bg-orange-500", amber: "bg-amber-500", lime: "bg-lime-500",
  emerald: "bg-emerald-500", teal: "bg-teal-500", sky: "bg-sky-500", blue: "bg-blue-500", violet: "bg-violet-500",
  pink: "bg-pink-500",
};

/** Mesma chave do backend (crm.models.customer_tag_model.tag_key): sem acento, minúsculas, sem pontuação. */
export function tagKey(name: string): string {
  return name.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase()
    .replace(/[^a-z0-9]+/g, " ").trim();
}

const TAGS_KEY = ["customer-tags"] as const;

export function useTags(withCounts = false) {
  return useQuery({
    queryKey: [...TAGS_KEY, withCounts ? "counts" : "plain"],
    queryFn: async () => (await api.get<CustomerTag[]>("/crm/tags/", { params: withCounts ? { counts: 1 } : {} })).data,
    staleTime: withCounts ? 0 : 60_000,
  });
}

/** Catálogo por chave, para mostrar nome e cor das tags de um cliente. */
export function useTagMap() {
  const { data } = useTags();
  return useMemo(() => new Map((data ?? []).map((tag) => [tag.key, tag])), [data]);
}

const apiError = (error: unknown, fallback: string) =>
  toast.error((error as { response?: { data?: { detail?: string } } })?.response?.data?.detail || fallback);

export function useCreateTag() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: { name: string; color?: string }) => (await api.post<CustomerTag>("/crm/tags/", data)).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: TAGS_KEY }),
    onError: (error) => apiError(error, "Não foi possível criar a tag."),
  });
}

export function useUpdateTag() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, ...data }: { id: string; name?: string; color?: string }) =>
      (await api.patch<CustomerTag>(`/crm/tags/${id}/`, data)).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: TAGS_KEY }),
    onError: (error) => apiError(error, "Não foi possível alterar a tag."),
  });
}

export function useDeleteTag() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => (await api.delete<{ removed_from: number }>(`/crm/tags/${id}/`)).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: TAGS_KEY });
      refreshTaggedLists(queryClient);
    },
    onError: (error) => apiError(error, "Não foi possível excluir a tag."),
  });
}

function refreshTaggedLists(queryClient: QueryClient) {
  queryClient.invalidateQueries({ queryKey: ["contacts"] });
  queryClient.invalidateQueries({ queryKey: ["contact"] });
  queryClient.invalidateQueries({ queryKey: ["conversations"] });
  queryClient.invalidateQueries({ queryKey: ["leads"] });
}

/** Põe as tags novas do cliente nas telas já carregadas (contato, conversas) sem esperar recarregar. */
function applyCustomerTags(queryClient: QueryClient, customerId: string, tags: string[]) {
  queryClient.setQueryData<ContactDetail>(["contact", customerId], (old) => (old ? { ...old, tags } : old));
  queryClient.setQueriesData<ConversationsData>({ queryKey: ["conversations"] }, (old) => {
    if (!old?.pages) return old;
    return {
      ...old,
      pages: old.pages.map((page) => ({
        ...page,
        results: page.results.map((c) => (c.customer === customerId ? { ...c, customer_tags: tags } : c)),
      })),
    };
  });
  queryClient.invalidateQueries({ queryKey: ["contacts"] });
  queryClient.invalidateQueries({ queryKey: ["leads"] });
  queryClient.invalidateQueries({ queryKey: [...TAGS_KEY, "counts"] });
}

export function useSetCustomerTags() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ customerId, tags }: { customerId: string; tags: string[] }) =>
      (await api.put<{ id: string; tags: string[] }>(`/crm/contacts/${customerId}/tags/`, { tags })).data,
    onSuccess: (data) => {
      applyCustomerTags(queryClient, data.id, data.tags);
      queryClient.invalidateQueries({ queryKey: ["contact-timeline", data.id] });
    },
    onError: (error) => apiError(error, "Não foi possível alterar as tags."),
  });
}
