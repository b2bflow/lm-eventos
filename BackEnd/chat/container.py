from utils.logger import logger
from chat.services.conversation_service import ConversationService
from chat.services.message_service import MessageService
from chat.interfaces.chat_service_interface import IConversationService, IMessageService

class ChatContainer:
    _conversation_service = None
    _message_service = None

    @classmethod
    def get_conversation_service(self) -> IConversationService:
        try:
            if not self._conversation_service:
                self._conversation_service = ConversationService()
                logger.info("[ChatContainer] ConversationService instanciado via Container.")
            return self._conversation_service
        except Exception as e:
            logger.error(f"[ChatContainer] Erro ao instanciar ConversationService: {e}")
            raise e

    @classmethod
    def get_message_service(self) -> IMessageService:
        try:
            if not self._message_service:
                self._message_service = MessageService()
                logger.info("[ChatContainer] MessageService instanciado via Container.")
            return self._message_service
        except Exception as e:
            logger.error(f"[ChatContainer] Erro ao instanciar MessageService: {e}")
            raise e

    @property
    def message_service(self) -> IMessageService:
        return self.get_message_service()