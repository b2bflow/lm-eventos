"""Apagar para todos, pelo painel, uma mensagem que a LM enviou no WhatsApp.

A Z-API apaga pelo messageId de cada mensagem: texto do painel guarda os ids em
raw_metadata.zapi_message_ids (o texto longo sai em várias partes); arquivo e mensagem enviada pelo
celular guardam o id em external_id. A mensagem continua salva (histórico da equipe), marcada como
apagada e fora do contexto da IA.
"""
from datetime import datetime, timedelta

import requests

from chat.models.message_model import MessageModel
from utils.logger import logger

# O WhatsApp só apaga para todos até ~2 dias e meio depois do envio.
DELETE_WINDOW = timedelta(hours=60)

DELETED_PREVIEW = "Mensagem apagada"


class MessageDeleteError(Exception):
    """A Z-API (WhatsApp) não apagou a mensagem."""


def sent_ids(message: MessageModel) -> list[str]:
    ids = (message.raw_metadata or {}).get("zapi_message_ids") or []
    if not ids and message.external_id:
        ids = [message.external_id]
    return [str(i) for i in ids if i]


def is_deleted(message: MessageModel) -> bool:
    return bool((message.raw_metadata or {}).get("deleted_at"))


def can_delete(message: MessageModel, now: datetime | None = None) -> bool:
    if message.direction != "OUTGOING" or is_deleted(message) or not sent_ids(message):
        return False
    created = message.created_at
    return not created or (now or datetime.utcnow()) - created.replace(tzinfo=None) <= DELETE_WINDOW


class MessageDeleteService:

    def __init__(self, chat=None, socket_adapter=None):
        from chat.gateways.adapters.socket_adapter import SocketAdapter
        from gateway.adapters.zapi_adapter import ZAPIClient
        self.chat = chat or ZAPIClient()
        self.socket_adapter = socket_adapter or SocketAdapter()

    def delete(self, message_id: str, user=None) -> MessageModel:
        message = MessageModel.objects(id=message_id).first()
        if not message:
            raise LookupError("Mensagem não encontrada.")
        if message.direction != "OUTGOING":
            raise ValueError("Só dá para apagar mensagens enviadas pela LM.")
        if is_deleted(message):
            raise ValueError("Mensagem já apagada.")
        ids = sent_ids(message)
        if not ids:
            raise ValueError("Esta mensagem não tem o registro do WhatsApp e não pode ser apagada pelo painel.")
        if not can_delete(message):
            raise ValueError("O WhatsApp só deixa apagar para todos até 2 dias depois do envio.")

        phone = getattr(message.customer, "phone", None) or getattr(message.conversation.customer, "phone", None)
        for zapi_id in ids:
            try:
                self.chat.delete_message(phone=phone, message_id=zapi_id)
            except requests.RequestException as e:
                logger.error(f"[MessageDelete] Z-API não apagou {zapi_id} da mensagem {message.id}: {e}")
                raise MessageDeleteError(
                    "O WhatsApp não apagou a mensagem. Tente de novo em instantes.") from e

        from chat.services.handover_service import user_display_name
        message.raw_metadata = {
            **(message.raw_metadata or {}),
            "deleted_at": datetime.utcnow().isoformat(),
            "deleted_by": user_display_name(user) if user else None,
        }
        message.hidden_from_ai = True
        message.updated_at = datetime.utcnow()
        message.save()

        conversation = message.conversation
        latest = MessageModel.objects(conversation=conversation, direction__ne="INTERNAL").order_by("-created_at").first()
        if latest and latest.id == message.id:
            conversation.update(last_message_content=DELETED_PREVIEW)

        from chat.serializers import MessageSerializer
        data = dict(MessageSerializer(message).data)
        try:
            self.socket_adapter.emit_message_updated(data)
        except Exception as e:
            logger.error(f"[MessageDelete] Falha ao avisar o painel da mensagem apagada {message.id}: {e}")
        return message
