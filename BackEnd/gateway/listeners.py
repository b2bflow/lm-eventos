from gateway.adapters.zapi_adapter import ZAPIClient
from utils.logger import logger
from events.bus import EventBus
from gateway.container import GatewayContainer


def handle_send_outgoing_message(payload: dict):
    try:
        to_phone = payload.get('phone')
        content = payload.get('content')

        gateway: ZAPIClient = GatewayContainer.chat()

        gateway.send_message(phone=to_phone, message=content)

        logger.info(f"[GatewayListeners] Mensagem enviada com sucesso para {to_phone}.")
    except Exception as e:
        logger.error(f"[GatewayListeners] Falha no listener de envio de mensagem: {e}")

EventBus.subscribe("SEND_OUTGOING_MESSAGE", handle_send_outgoing_message)