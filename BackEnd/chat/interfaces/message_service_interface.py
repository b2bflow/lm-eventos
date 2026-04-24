from abc import ABC, abstractmethod
from typing import Any

class IMessageService(ABC):
    """
    Interface atualizada para o MessageService.
    Define os contratos para o processamento de entrada e saída de mensagens,
    além da recuperação de histórico.
    """

    @abstractmethod
    def handle(self, **kwargs) -> dict:
        """
        Lida com a entrada bruta de mensagens do gateway, processa mídias 
        e retorna um dicionário padronizado.
        """
        pass

    @abstractmethod
    def get_messages_by_conversation(self, conversation_id: str) -> Any:
        """
        Recupera todas as mensagens associadas a uma conversa específica.
        """
        pass

    @abstractmethod
    def get_messages_by_customer(self, customer_id: str) -> Any:
        """
        Recupera todas as mensagens associadas a um paciente específico.
        """
        pass

    @abstractmethod
    def process_incoming_message(self, phone: str, content: str, external_id: str = None, raw_metadata: dict = None) -> Any:
        """
        Processa uma mensagem de texto já estruturada vinda do usuário final, 
        cria/recupera o paciente e a conversa, e salva a mensagem no banco.
        """
        pass

    @abstractmethod
    def execute_operator_message(self, conversation_id: str, content: str, sender_id: str) -> Any:
        """
        Salva e despacha uma mensagem originada por um operador (atendente humano).
        """
        pass

    @abstractmethod
    def execute_bot_message(self, conversation_id: str, content: str) -> Any:
        """
        Salva e despacha uma mensagem originada pela IA (assistente bot).
        """
        pass