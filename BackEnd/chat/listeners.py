from utils.logger import logger
from events.bus import EventBus
from chat.container import ChatContainer


def handle_whatsapp_message_received(payload: dict):
    try:
        phone = payload.get('phone')
        content = payload.get('content')
        external_id = payload.get('external_id') 
        raw_metadata = payload.get('raw_data') 

        if not phone or not content:
            logger.warning("[ChatListeners] Payload inválido. Telefone ou conteúdo ausente.")
            return

        message_service = ChatContainer.get_message_service()
        message_service.process_incoming_message(
            phone=phone, 
            content=content, 
            external_id=external_id, 
            raw_metadata=raw_metadata
        )
        logger.info(f"[ChatListeners] Mensagem processada para o telefone {phone}.")
    except Exception as e:
        logger.error(f"[ChatListeners] Falha no listener de receção: {e}")

EventBus.subscribe("WHATSAPP_MESSAGE_RECEIVED", handle_whatsapp_message_received)