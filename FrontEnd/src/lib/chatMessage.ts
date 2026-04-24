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
