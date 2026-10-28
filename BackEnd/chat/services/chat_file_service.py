"""Arquivos enviados pelo operador na aba WhatsApp: guardados no GridFS e servidos por link assinado."""
import os
from urllib.parse import quote

from bson import ObjectId
from django.core import signing

from chat.models.chat_file_model import ChatFile

FILE_SIGNING_SALT = "lm-chat-file"
FILE_LINK_MAX_AGE = 180 * 24 * 3600  # mesmo prazo do link do PDF da proposta


def public_base_url() -> str:
    """URL pública desta API (BACKEND_PUBLIC_URL); vazio quando é local, porque a Z-API não alcança."""
    base = os.getenv("BACKEND_PUBLIC_URL", "").strip().rstrip("/")
    if not base.startswith("https://") or "localhost" in base or "127.0.0.1" in base:
        return ""
    return base


def save_chat_file(conversation, uploaded_file, file_name: str, content_type: str) -> ChatFile:
    uploaded_file.seek(0)
    chat_file = ChatFile(conversation=conversation, file_name=file_name, content_type=content_type,
                         size=uploaded_file.size)
    chat_file.data.new_file(content_type=content_type, filename=file_name)
    for chunk in uploaded_file.chunks():
        chat_file.data.write(chunk)
    chat_file.data.close()
    return chat_file.save()


def signed_file_url(chat_file: ChatFile) -> str:
    """Link que abre sem login: a Z-API baixa por ele e o painel mostra o arquivo na conversa."""
    token = signing.dumps(str(chat_file.id), salt=FILE_SIGNING_SALT)
    base = os.getenv("BACKEND_PUBLIC_URL", "").strip().rstrip("/")
    return f"{base}/api/v1/chat/files/{chat_file.id}/{quote(chat_file.file_name)}?t={token}"


def get_signed_file(file_id: str, token: str | None) -> ChatFile | None:
    if not token or not ObjectId.is_valid(file_id):
        return None
    try:
        if signing.loads(token, salt=FILE_SIGNING_SALT, max_age=FILE_LINK_MAX_AGE) != file_id:
            return None
    except signing.BadSignature:
        return None
    return ChatFile.objects(id=file_id).first()
