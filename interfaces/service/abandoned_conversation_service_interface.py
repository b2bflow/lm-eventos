from abc import ABC, abstractmethod
from database.models.customer_model import Customer


class IAbandonedConversationService(ABC):
    """
    Interface para o serviço de lógica de negócio de conversas abandonadas.
    """

    @abstractmethod
    def is_abandoned_conversation(self, customer: Customer, hours_absence: int) -> bool:
        """
        Verifica se uma conversa de um customer é considerada abandonada.

        Args:
            customer: Objeto Customer do MongoEngine
            hours_absence: Número de horas para considerar como abandonada

        Returns:
            bool: True se a conversa é considerada abandonada
        """
        pass

    @abstractmethod
    def get_abandoned_conversations(self, hours_absence: int) -> list[dict]:
        """
        Retorna todas as conversas que são consideradas abandonadas.

        Args:
            hours_absence: Número de horas para considerar como abandonada

        Returns:
            list[dict]: Lista de customers com conversas abandonadas
        """
        pass
