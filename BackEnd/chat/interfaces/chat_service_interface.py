from abc import ABC, abstractmethod
from typing import Any, Optional

class IConversationService(ABC):
    @abstractmethod
    def update_conversation(self, conversation_id: str, data: dict, user: Any = None) -> Any:
        pass

class IMessageService(ABC):
    @abstractmethod
    def process_incoming_message(self, phone: str, content: str, external_id: str = None, raw_metadata: dict = None) -> Any:
        pass

    @abstractmethod
    def execute_operator_message(self, conversation_id: str, content: str, sender_id: str) -> Any:
        pass

    @abstractmethod
    def execute_bot_message(self, conversation_id: str, content: str) -> Any:
        pass


    def handle(self, **kwargs) -> dict:
        pass

    def get_messages_by_conversation(self, conversation_id: str):
        pass

    def get_messages_by_customer(self, customer_id: str):
        pass


    def _save_and_notify(self, conversation_id: str, content: str, direction: str, sender_role: str, external_id: str = None, raw_metadata: dict = None) -> Any:
        pass

    def _process_outgoing_message(self, conversation_id: str, content: str, sender_role: str, sender_id: Optional[str] = None):
        pass