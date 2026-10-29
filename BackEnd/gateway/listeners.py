from gateway.adapters.zapi_adapter import ZAPIClient
from utils.logger import logger
from events.bus import EventBus
from gateway.container import GatewayContainer


def handle_send_outgoing_message(payload: dict):
    try:
        to_phone = payload.get('phone')
        content = payload.get('content')

        gateway: ZAPIClient = GatewayContainer().chat

        # send_message devolve False quando a Z-API recusa ou o telefone é inválido: não logar sucesso
        # Texto do operador sai inteiro, com as quebras de linha; o resto segue dividido em frases.
        if gateway.send_message(phone=to_phone, message=content, split=not payload.get('keep_format')):
            logger.info(f"[GatewayListeners] Mensagem enviada com sucesso para {to_phone}.")
            _store_sent_ids(payload.get('message_id'), getattr(gateway, 'last_sent_ids', None))
        else:
            logger.error(f"[GatewayListeners] Mensagem NÃO enviada para {to_phone} (Z-API recusou ou telefone inválido).")
    except Exception as e:
        logger.error(f"[GatewayListeners] Falha no listener de envio de mensagem: {e}")

def _store_sent_ids(message_id: str | None, sent_ids: list[str] | None) -> None:
    """Guarda na mensagem do painel o messageId de cada parte enviada: é o que permite apagar depois."""
    if not message_id or not sent_ids:
        return
    try:
        from chat.models.message_model import MessageModel
        message = MessageModel.objects(id=message_id).first()
        if not message:
            return
        message.raw_metadata = {**(message.raw_metadata or {}), "zapi_message_ids": list(sent_ids)}
        if not message.external_id and not MessageModel.objects(external_id=sent_ids[0]).first():
            message.external_id = sent_ids[0]
        message.status = "SENT_TO_GATEWAY"
        message.save()
        # O painel já mostra a bolha: agora ela ganha a opção de apagar.
        from chat.gateways.adapters.socket_adapter import SocketAdapter
        from chat.serializers import MessageSerializer
        SocketAdapter().emit_message_updated(dict(MessageSerializer(message).data))
    except Exception as e:
        # A mensagem já saiu para o cliente; sem o id ela só não poderá ser apagada pelo painel.
        logger.error(f"[GatewayListeners] Falha ao guardar o id da Z-API na mensagem {message_id}: {e}")


EventBus.subscribe("SEND_OUTGOING_MESSAGE", handle_send_outgoing_message)