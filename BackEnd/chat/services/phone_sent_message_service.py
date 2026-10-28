"""Mensagens que a equipe manda direto pelo WhatsApp da LM (celular ou WhatsApp Web), fora da plataforma.

Com a opção "Notificar as enviadas por mim também" ligada na Z-API, o webhook de recebimento chega
também com fromMe=True para tudo o que sai do número. O que a plataforma enviou pela API (IA, menu,
operador pelo painel, PDF) vem com fromApi=True e já está salvo: é ignorado. O resto foi digitado no
aparelho: entra na conversa como mensagem do operador e, se a IA estava atendendo, a conversa passa
para OPERADOR (a IA para de responder esse cliente).
"""
from datetime import datetime, timedelta

from chat.models.message_model import MessageModel
from utils.logger import logger
from utils.safe_url import safe_media_url

# Sem fromApi no payload, texto igual a uma saída da plataforma nesse intervalo é o eco dela.
ECHO_WINDOW = timedelta(minutes=2)

TAKEOVER_TEXT = ("Mensagem enviada direto pelo WhatsApp. Atendimento passou para operador e a IA "
                 "foi pausada nesta conversa.")

# (message_type, chave no payload da Z-API, chave da URL, texto quando não há legenda)
MEDIA_KINDS = (
    ("image", "image", "imageUrl", "[Imagem]"),
    ("video", "video", "videoUrl", "[Vídeo]"),
    ("file", "document", "documentUrl", "[Arquivo]"),
    ("audio", "audio", "audioUrl", "[Áudio]"),
)


class PhoneSentMessageService:

    def __init__(self, chat=None, audio_transcription=None):
        from gateway.adapters.zapi_adapter import ZAPIClient
        self.chat = chat or ZAPIClient()
        self._audio_transcription = audio_transcription

    @property
    def audio_transcription(self):
        if self._audio_transcription is None:
            from ai_agents.clients.openai_client import OpenIAClient
            from gateway.service.audio_transcription_service import AudioTranscriptionService
            self._audio_transcription = AudioTranscriptionService(self.chat, OpenIAClient())
        return self._audio_transcription

    def matches(self, data: dict) -> bool:
        """Enviada pelo aparelho para um contato (grupo, status e canal ficam de fora)."""
        if not data.get("fromMe") or data.get("fromApi"):
            return False
        if data.get("isGroup") or data.get("isNewsletter") or data.get("broadcast"):
            return False
        phone = self.chat.get_phone(**data)
        return bool(phone) and ("@" not in phone or self.chat.is_lid(phone))

    def process(self, data: dict) -> MessageModel | None:
        phone = self.chat.get_phone(**data)
        extracted = self._content(data)
        if not extracted:
            logger.info(f"[PhoneSentMessage] Envio pelo WhatsApp para {phone} sem conteúdo registrável (reação, figurinha...).")
            return None
        content, message_type, media_url = extracted

        external_id = data.get("messageId") or data.get("id")
        if external_id and MessageModel.objects(external_id=external_id).first():
            return None

        from chat.container import ChatContainer
        from crm.container import CrmContainer
        customer_service = CrmContainer.get_customer_service()
        message_service = ChatContainer.get_message_service()
        conversation_repo = message_service.conversation_repo

        customer = customer_service.get_customer_by_phone(phone)
        if not customer:
            # chatName é o nome do contato na agenda do aparelho; senderName seria o da própria LM.
            customer = customer_service.register_customer(
                data={"name": data.get("chatName") or f"WhatsApp {phone}", "phone": phone}
            )
        customer_id = customer.get("id") if isinstance(customer, dict) else str(customer.id)

        conversation = conversation_repo.get_active_conversation(customer_id)
        if not conversation:
            conversation = conversation_repo.create_conversation(customer_id)
        elif "fromApi" not in data and message_type == "text" and self._is_platform_echo(conversation, content):
            logger.info(f"[PhoneSentMessage] Eco de mensagem da plataforma para {phone} ignorado.")
            return None

        message = message_service._save_and_notify(
            conversation_id=str(conversation.id),
            content=content,
            direction="OUTGOING",
            sender_role="OPERATOR",
            external_id=external_id,
            raw_metadata={**data, "sent_from_phone": True},
            message_type=message_type,
            media_url=media_url,
            status="SENT_TO_GATEWAY",
        )

        # A equipe respondeu: a conversa deixa de pedir atenção.
        conversation.last_message_content = message_service._preview(content, message_type, data)
        conversation.updated_at = datetime.now()
        conversation.needs_attention = False
        conversation.unread_count = 0
        conversation_repo.update_conversation(conversation)

        if conversation.ai_active or conversation.tag == "AGENTE":
            ChatContainer.get_handover_service().take_over(conversation, TAKEOVER_TEXT)
            logger.info(f"[PhoneSentMessage] Conversa {conversation.id} passou para OPERADOR (resposta pelo WhatsApp).")
        return message

    def _content(self, data: dict) -> tuple[str, str, str | None] | None:
        """(texto salvo, message_type, media_url), ou None para o que não vale registrar."""
        text = data.get("text")
        if isinstance(text, dict) and (text.get("message") or "").strip():
            return text["message"], "text", None

        for kind, key, url_key, label in MEDIA_KINDS:
            media = data.get(key)
            if not isinstance(media, dict) or not media.get(url_key):
                continue
            caption = (media.get("caption") or "").strip()
            if kind == "audio":
                caption = self.audio_transcription.transcribe(**data) or ""
            elif kind == "file" and not caption:
                caption = f"{label} {media.get('fileName') or ''}".strip()
            return caption or label, kind, safe_media_url(media[url_key])

        location = data.get("location")
        if isinstance(location, dict):
            name = location.get("name") or location.get("address") or ""
            return f"[Localização] {name}".strip(), "text", None

        contact = data.get("contact")
        if isinstance(contact, dict):
            return f"[Contato] {contact.get('displayName') or ''}".strip(), "text", None
        return None

    @staticmethod
    def _is_platform_echo(conversation, text: str) -> bool:
        """A plataforma quebra os textos em frases: o eco é um pedaço de uma saída recente."""
        needle = text.strip().rstrip(".").strip()
        if not needle:
            return False
        recent = MessageModel.objects(
            conversation=conversation, direction="OUTGOING", created_at__gte=datetime.utcnow() - ECHO_WINDOW,
        )
        return any(needle in (m.content or "") for m in recent)
