/**
 * URL de mídia ou anexo que pode ir para `src`/`href` (img, iframe, audio, link).
 *
 * Só http(s) absoluto ou caminho da própria API (`/api/...`). Qualquer outro esquema
 * (`javascript:`, `data:`, `vbscript:`...) vira `undefined`: o texto de uma mensagem do WhatsApp
 * chega aqui e um `javascript:` num iframe roda no domínio do painel com o login de quem abriu.
 * Espelha `utils/safe_url.py` do backend.
 */
export function safeMediaUrl(url?: string | null): string | undefined {
  if (typeof url !== "string") return undefined;
  const trimmed = url.trim();
  if (!trimmed || trimmed.length > 2048 || /[\r\n\t\0]/.test(trimmed)) return undefined;
  if (trimmed.startsWith("/api/") && !trimmed.startsWith("//")) {
    return `${import.meta.env.VITE_API_URL || ""}${trimmed}`;
  }
  try {
    const parsed = new URL(trimmed);
    if ((parsed.protocol === "http:" || parsed.protocol === "https:") && parsed.host) return trimmed;
  } catch {
    return undefined;
  }
  return undefined;
}
