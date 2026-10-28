import { safeMediaUrl } from "./safeUrl";

/** note e event: mensagens internas da equipe (direction INTERNAL), nunca enviadas ao cliente. */
export type ChatMessageType = "text" | "image" | "audio" | "video" | "file" | "note" | "event";

export interface ChatMenuButton {
  id: string;
  label: string;
}

export interface ChatMessage {
  id: string;
  content: string;
  direction: "INCOMING" | "OUTGOING" | "INTERNAL";
  role: string;
  created_at: string;
  time: string;
  conversation?: string;
  message_type: ChatMessageType;
  media_url?: string | null;
  buttons?: ChatMenuButton[];
  /** Autor da nota interna ou da ação da equipe (direction INTERNAL). */
  author_name?: string | null;
  /** Enviada pela equipe direto no WhatsApp (celular/Web), fora da plataforma. */
  sent_from_phone?: boolean;
}

export function normalizeChatMessageContent(content: unknown): string {
  if (typeof content !== "string") {
    return String(content ?? "");
  }

  const trimmed = content.trim();
  if (!trimmed.startsWith("<kwargs>") || !trimmed.endsWith("</kwargs>")) {
    return content;
  }

  const buttonMessageMatch = trimmed.match(
    /buttonsResponseMessage['"]?\s*:\s*\{[\s\S]*?['"]message['"]?\s*:\s*['"]([^'"]+)['"]/
  );

  if (buttonMessageMatch?.[1]) {
    return buttonMessageMatch[1];
  }

  const genericMessageMatch = trimmed.match(/['"]message['"]?\s*:\s*['"]([^'"]+)['"]/);
  if (genericMessageMatch?.[1]) {
    return genericMessageMatch[1];
  }

  return content;
}

const MEDIA_TAG = /^\s*<(image|file)-url>([\s\S]*?)<\/\1-url>\s*([\s\S]*)$/;

/**
 * Separa mídia e legenda. O backend grava `message_type`/`media_url`; mensagens antigas
 * só têm o texto `<image-url>…</image-url> legenda` (formato que a IA lê) e também são aceitas.
 */
export function parseMediaContent(
  content: string,
  messageType?: string | null,
  mediaUrl?: string | null
): { type: ChatMessageType; url: string | null; text: string } {
  const tag = content.match(MEDIA_TAG);
  if (tag) {
    const type: ChatMessageType = tag[1] === "image" ? "image" : "file";
    // Formato antigo (<image-url> no texto): o cliente pode digitar a tag, então a URL passa pelo
    // mesmo filtro da mídia (só http/https) antes de virar src/href.
    return { type, url: safeMediaUrl(mediaUrl || tag[2]) || null, text: tag[3].trim() };
  }
  const type = (messageType as ChatMessageType) || "text";
  return { type, url: safeMediaUrl(mediaUrl) || null, text: normalizeChatMessageContent(content) };
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function toChatMessage(raw: any): ChatMessage {
  const parsed = parseMediaContent(String(raw.content ?? ""), raw.message_type, raw.media_url);
  return {
    id: String(raw.id),
    content: parsed.text,
    direction: raw.direction,
    role: raw.role,
    created_at: raw.created_at,
    time: raw.created_at
      ? new Date(raw.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
      : "",
    conversation: raw.conversation_id || raw.conversation,
    message_type: parsed.type,
    media_url: parsed.url,
    buttons: Array.isArray(raw.buttons) ? raw.buttons : undefined,
    author_name: raw.author_name ?? null,
    sent_from_phone: !!raw.raw_metadata?.sent_from_phone,
  };
}
