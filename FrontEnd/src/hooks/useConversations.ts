import { useCallback, useEffect } from "react";
import { InfiniteData, QueryClient, useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import api from "@/services/api";
import { normalizeChatMessageContent, parseMediaContent, toChatMessage, type ChatMessage } from "@/lib/chatMessage";

export interface Conversa {
  final_customer_status?: string;
  past_conversations?: { id: string; created_at: string; status: string; final_customer_status?: string }[];
  id: string;
  customer: string;
  customer_name: string;
  customer_phone: string;
  last_message_content: string;
  last_interaction_at: string;
  status: "OPEN" | "CLOSED" | "ARCHIVED";
  tag: string;
  unread_count?: number;
  customer_status?: string;
  needs_attention?: boolean;
  assignee?: "sdr" | "erica" | "lucia" | null;
  handover_by_name?: string | null;
  handover_at?: string | null;
  customer_product?: string | null;
  customer_human_operator?: boolean;
}

export interface CursorPage<T> {
  results: T[];
  next_cursor: string | null;
  has_more: boolean;
  total?: number;
}

export type ConversationTab = "OPEN" | "CLOSED";
export type ConversationsData = InfiniteData<CursorPage<Conversa>, string | null>;
export type MessagesData = InfiniteData<CursorPage<ChatMessage>, string | null>;

/** Evento `new_message` emitido pelo backend via Socket.IO. */
export interface NewMessageEvent {
  id: string;
  conversation_id?: string;
  conversation?: string;
  content: string;
  direction: "INCOMING" | "OUTGOING" | "INTERNAL";
  role: string;
  message_type?: string;
  media_url?: string | null;
  buttons?: { id: string; label: string }[] | null;
  author_name?: string | null;
  created_at: string;
}

const PAGE_SIZE = 20;
const MESSAGES_PAGE_SIZE = 30;

export const conversationsKey = (tab: ConversationTab, search: string, assignee = "") =>
  ["conversations", { tab, search, assignee }] as const;

async function fetchConversations(tab: ConversationTab, search: string, cursor: string | null, assignee = "") {
  const params: Record<string, string | number> = { page_size: PAGE_SIZE, status: tab };
  if (search) params.search = search;
  if (assignee) params.assignee = assignee;
  if (cursor) params.cursor = cursor;
  const { data } = await api.get<CursorPage<Conversa>>("/chat/conversations/", { params });
  return data;
}

/** Junta as páginas removendo repetidos por id (a primeira ocorrência, mais recente, vence). */
export function flattenUnique<T extends { id: string }>(data?: InfiniteData<CursorPage<T>, unknown>): T[] {
  const seen = new Set<string>();
  const out: T[] = [];
  for (const page of data?.pages ?? []) {
    for (const item of page.results) {
      if (seen.has(item.id)) continue;
      seen.add(item.id);
      out.push(item);
    }
  }
  return out;
}

function previewFromEvent(event: NewMessageEvent): string {
  const parsed = parseMediaContent(event.content, event.message_type, event.media_url);
  if (parsed.type === "image") return parsed.text ? `[Imagem] ${parsed.text}` : "[Imagem]";
  if (parsed.type === "file") return "[Arquivo]";
  if (parsed.type === "audio") return `[Áudio] ${parsed.text}`.trim();
  return normalizeChatMessageContent(event.content);
}

/**
 * Aplica uma mensagem nova a todas as listas de conversas em cache: atualiza a conversa e a leva
 * para o topo da primeira página. Se a conversa ainda não foi carregada, recarrega a lista.
 */
export function applyNewMessageToConversations(queryClient: QueryClient, event: NewMessageEvent) {
  const conversationId = event.conversation_id || event.conversation;
  // Nota interna e eventos da equipe não mudam a prévia nem a ordem da lista.
  if (!conversationId || event.direction === "INTERNAL") return;
  let missing = false;

  queryClient.setQueriesData<ConversationsData>({ queryKey: ["conversations"] }, (old) => {
    if (!old?.pages?.length) return old;
    let found: Conversa | undefined;
    const pages = old.pages.map((page) => ({
      ...page,
      results: page.results.filter((c) => {
        if (c.id === conversationId) {
          found = c;
          return false;
        }
        return true;
      }),
    }));
    if (!found) {
      missing = true;
      return old;
    }
    const updated: Conversa = {
      ...found,
      last_message_content: previewFromEvent(event),
      last_interaction_at: event.created_at,
      unread_count: (found.unread_count || 0) + (event.direction === "INCOMING" ? 1 : 0),
    };
    pages[0] = { ...pages[0], results: [updated, ...pages[0].results] };
    return { ...old, pages };
  });

  if (missing) refreshFirstConversationPages(queryClient);
}

/** Altera campos de uma conversa em todas as listas em cache (ex.: marcar como lida). */
export function patchConversationInCache(queryClient: QueryClient, id: string, patch: Partial<Conversa>) {
  queryClient.setQueriesData<ConversationsData>({ queryKey: ["conversations"] }, (old) => {
    if (!old?.pages) return old;
    return {
      ...old,
      pages: old.pages.map((page) => ({
        ...page,
        results: page.results.map((c) => (c.id === id ? { ...c, ...patch } : c)),
      })),
    };
  });
}

/**
 * Recarrega só a primeira página de cada lista em cache e tira das páginas seguintes as conversas
 * que voltaram nela (subiram para o topo). Evita refazer todas as páginas já roladas.
 */
export async function refreshFirstConversationPages(queryClient: QueryClient) {
  const queries = queryClient.getQueriesData<ConversationsData>({ queryKey: ["conversations"] });
  await Promise.all(
    queries.map(async ([key, data]) => {
      if (!data?.pages?.length) return;
      const filters = (key[1] ?? {}) as { tab?: ConversationTab; search?: string; assignee?: string };
      const fresh = await fetchConversations(filters.tab ?? "OPEN", filters.search ?? "", null, filters.assignee ?? "");
      const freshIds = new Set(fresh.results.map((c) => c.id));
      queryClient.setQueryData<ConversationsData>(key, (old) => {
        if (!old) return old;
        const rest = old.pages.slice(1).map((page) => ({
          ...page,
          results: page.results.filter((c) => !freshIds.has(c.id)),
        }));
        // Mantém o cursor da primeira página antiga para não pular itens já paginados.
        return { ...old, pages: [{ ...fresh, next_cursor: old.pages[0].next_cursor, has_more: old.pages[0].has_more }, ...rest] };
      });
    })
  );
}

export function useConversations(tab: ConversationTab, search: string, assignee = "") {
  const queryClient = useQueryClient();
  const query = useInfiniteQuery({
    queryKey: conversationsKey(tab, search, assignee),
    queryFn: ({ pageParam }) => fetchConversations(tab, search, pageParam, assignee),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => (last.has_more ? last.next_cursor : undefined),
  });

  const refresh = useCallback(() => refreshFirstConversationPages(queryClient), [queryClient]);

  useEffect(() => {
    const timer = window.setInterval(refresh, 30000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  return { ...query, conversations: flattenUnique(query.data), total: query.data?.pages[0]?.total };
}

export const messagesKey = (conversationId: string | null, scope: "conversation" | "customer") =>
  ["messages", conversationId, scope] as const;

export function useMessages(conversationId: string | null, customerId: string | undefined, fullHistory: boolean) {
  const scope = fullHistory ? "customer" : "conversation";
  const query = useInfiniteQuery({
    queryKey: messagesKey(conversationId, scope),
    queryFn: async ({ pageParam }) => {
      const params: Record<string, string | number> = { page_size: MESSAGES_PAGE_SIZE };
      if (fullHistory && customerId) params.customer = customerId;
      else params.conversation = conversationId as string;
      if (pageParam) params.cursor = pageParam;
      const { data } = await api.get<CursorPage<unknown>>("/chat/messages/", { params });
      return { ...data, results: data.results.map(toChatMessage) } as CursorPage<ChatMessage>;
    },
    initialPageParam: null as string | null,
    getNextPageParam: (last) => (last.has_more ? last.next_cursor : undefined),
    enabled: !!conversationId && (!fullHistory || !!customerId),
  });

  // Página 0 = mais recentes; as seguintes são mais antigas. Exibe em ordem cronológica.
  const messages: ChatMessage[] = [];
  const seen = new Set<string>();
  const pages = query.data?.pages ?? [];
  for (let i = pages.length - 1; i >= 0; i--) {
    for (const m of pages[i].results) {
      if (seen.has(m.id)) continue;
      seen.add(m.id);
      messages.push(m);
    }
  }
  return { ...query, messages };
}

/** Acrescenta uma mensagem recebida por socket ao fim da conversa em cache. */
export function appendMessageToCache(queryClient: QueryClient, event: NewMessageEvent) {
  const conversationId = event.conversation_id || event.conversation;
  if (!conversationId) return;
  const message = toChatMessage(event);
  queryClient.setQueryData<MessagesData>(messagesKey(conversationId, "conversation"), (old) => {
    if (!old?.pages?.length) return old;
    if (old.pages.some((p) => p.results.some((m) => m.id === message.id))) return old;
    const pages = [...old.pages];
    pages[0] = { ...pages[0], results: [...pages[0].results, message] };
    return { ...old, pages };
  });
}
