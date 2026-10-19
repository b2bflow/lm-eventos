"""URLs de mídia e anexos exibidas no painel (img, iframe, link).

Só http(s) absoluto ou caminho da própria API (/api/...). Qualquer outro esquema (javascript:,
data:, vbscript:, file:) vira None: o painel renderiza essas URLs e um `javascript:` num iframe
roda no domínio do app com o login de quem abriu a conversa.
"""
from urllib.parse import urlsplit

MAX_URL_LENGTH = 2048


def safe_media_url(url) -> str | None:
    if not isinstance(url, str):
        return None
    url = url.strip()
    if not url or len(url) > MAX_URL_LENGTH or any(ch in url for ch in "\r\n\t\x00"):
        return None
    if url.startswith("/api/") and not url.startswith("//"):
        return url
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if parts.scheme.lower() in ("http", "https") and parts.netloc:
        return url
    return None
