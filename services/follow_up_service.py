from datetime import datetime, timedelta
from database.models.customer_model import Customer
from database.models.message_model import Message
from interfaces.clients.database_interface import IDatabase


class FollowUpService:
    """
    Serviço responsável pela lógica de negócio relacionada a conversas abandonadas.

    Define o que é uma conversa abandonada e fornece métodos para identificá-las.
    """

    def __init__(self, database_client: IDatabase):
        self.db = database_client

    def is_abandoned_conversation(self, customer: Customer, hours_absence: int) -> bool:
        """
        Verifica se uma conversa de um customer é considerada abandonada.

        Regras de conversa abandonada:
        1. A flag "needs_follow_up" deve ser True
        2. A flag "follow_up_done" deve ser False
        3. A última mensagem deve ter role = "assistant"
        4. A última mensagem deve ter been created antes de (agora - hours_absence)

        Args:
            customer: Objeto Customer do MongoEngine
            hours_absence: Número de horas para considerar como abandonada

        Returns:
            bool: True se a conversa é considerada abandonada
        """
        # Verifica flags básicas
        if not customer.needs_follow_up or customer.follow_up_done:
            return False

        # Busca a última mensagem
        last_message = (
            Message.objects(customer_id=customer.id).order_by("-created_at").first()
        )

        print(f"Customer: {customer.phone} - Last message: {last_message.to_dict() if last_message else 'None'}")

        if not last_message:
            print(f"Customer: {customer.phone} - No messages found")
            return False

        # Verifica se o role é "assistant"
        if last_message.role != "assistant":
            return False

        # Verifica se o tempo de ausência foi excedido
        time_threshold = datetime.now() - timedelta(hours=hours_absence)

        print(f"Customer: {customer.phone} - Last message at: {last_message.created_at} - Threshold: {time_threshold}")

        if last_message.created_at >= time_threshold:
            return False

        return True

    def get_abandoned_conversations(self, hours_absence: int) -> list[dict]:
        """
        Retorna todas as conversas que são consideradas abandonadas.

        Args:
            hours_absence: Número de horas para considerar como abandonada

        Returns:
            list[dict]: Lista de customers com conversas abandonadas
        """
        with self.db.get_connection_context():
            # Busca todos os customers que atendem aos critérios básicos
            customers = Customer.objects(needs_follow_up=True, follow_up_done=False)

            abandoned_customers = []

            for customer in customers:
                if self.is_abandoned_conversation(customer, hours_absence):
                    abandoned_customers.append(customer.to_dict())

            return abandoned_customers
